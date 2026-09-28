"""LLM integration with a hard rule-based fallback.

The LLM (any OpenAI-compatible endpoint) may:
  - parse free-text experiment goals into structured contract fields,
  - explain incidents in natural language,
  - summarize reports.

It may NOT decide permissions, detection, integrity, or execution. When no LLM
is configured (or it fails), RuleBasedReasoner produces the same structured
outputs deterministically — the system never blocks on an LLM.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

import httpx

from ..core.config import settings


class Reasoner(Protocol):
    name: str

    def parse_goal(self, text: str) -> dict[str, Any]: ...
    def explain_incident(self, incident_type: str, evidence: list[str]) -> str: ...


_MODEL_RE = re.compile(r"\b([A-Za-z][\w.-]*-\d+(?:\.\d+)?[BbMm])\b")
_METRIC_RE = re.compile(r"(macro[- ]?f1|f1|accuracy|auc)\s*([><]=?|==)\s*(0?\.\d+|\d+\.?\d*)", re.IGNORECASE)
_VRAM_RE = re.compile(r"(?:vram|显存)\s*(?:under|below|<=?|<|不超过|低于)?\s*(\d+)\s*(gb|gib)", re.IGNORECASE)
_HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h|小时)", re.IGNORECASE)
_STEPS_RE = re.compile(r"(\d+)\s*steps?", re.IGNORECASE)


class RuleBasedReasoner:
    """Deterministic goal parser and incident explainer. Always available."""

    name = "rule-based"

    def parse_goal(self, text: str) -> dict[str, Any]:
        result: dict[str, Any] = {"description": text.strip()}

        model = _MODEL_RE.search(text)
        if model:
            result["model"] = model.group(1)
        metric = _METRIC_RE.search(text)
        if metric:
            name = metric.group(1).lower().replace("-", "_").replace(" ", "_")
            result["metric"] = {"name": name, "operator": _normalize_op(metric.group(2)), "target": float(metric.group(3))}
        vram = _VRAM_RE.search(text)
        if vram:
            result["max_vram_gb"] = float(vram.group(1))
        hours = _HOURS_RE.search(text)
        if hours:
            result["max_duration_hours"] = float(hours.group(1))
        steps = _STEPS_RE.search(text)
        if steps:
            result["max_steps"] = int(steps.group(1))

        lowered = text.lower()
        if "eval" in lowered and "finetune" not in lowered and "fine-tune" not in lowered:
            result["type"] = "eval"
        elif any(w in lowered for w in ("finetune", "fine-tune", "fine tune", "微调", "train", "训练")):
            result["type"] = "finetune"
        else:
            result["type"] = "custom"

        dataset = re.search(r"dataset[/:\s]+([\w-]+(?:\.[\w-]+)*)", text)
        if dataset:
            result["dataset"] = f"dataset/{dataset.group(1)}"
        return result

    def explain_incident(self, incident_type: str, evidence: list[str]) -> str:
        joined = "; ".join(evidence[:3])
        explanations = {
            "CUDA_OOM": (
                "The training process exhausted GPU memory during allocation. "
                f"Evidence: {joined}. Standard remediation is to shrink per-device batch size, "
                "compensate with gradient accumulation to preserve the effective batch, and "
                "enable gradient checkpointing."
            ),
            "NAN_LOSS": (
                "The loss became non-finite, indicating numerical instability (usually an "
                f"over-large learning rate or gradient spike). Evidence: {joined}. Remediation: "
                "roll back to the last stable checkpoint, lower the learning rate, and clip gradients."
            ),
            "PROCESS_CRASH": (
                f"The training process terminated abnormally. Evidence: {joined}. "
                "Resuming from the latest checkpoint is the safe default."
            ),
            "DISK_LOW": f"Disk space below safety threshold. Evidence: {joined}.",
            "GPU_UNAVAILABLE": f"No GPU runtime visible. Evidence: {joined}.",
        }
        return explanations.get(incident_type, f"Incident {incident_type}. Evidence: {joined}.")


def _normalize_op(op: str) -> str:
    return {">": ">", "<": "<", ">=": ">=", "<=": "<=", "==": "==", "=": "=="}.get(op, op)


class OpenAICompatibleReasoner:
    """Optional LLM-backed reasoner; degrades to rules on any failure."""

    name = "openai-compatible"

    def __init__(self) -> None:
        self._fallback = RuleBasedReasoner()

    @property
    def available(self) -> bool:
        return bool(settings.llm_base_url and settings.llm_model)

    def _chat(self, system: str, user: str) -> str | None:
        if not self.available:
            return None
        try:
            resp = httpx.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key or 'none'}"},
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
                timeout=settings.llm_timeout_s,
            )
            resp.raise_for_status()
            return str(resp.json()["choices"][0]["message"]["content"])
        except Exception:
            return None

    def parse_goal(self, text: str) -> dict[str, Any]:
        system = (
            "Extract experiment parameters as compact JSON with optional keys: "
            "model (str), type (finetune|eval|custom), dataset (str), "
            "metric {name, operator, target}, max_vram_gb (number), "
            "max_duration_hours (number), max_steps (int). JSON only."
        )
        raw = self._chat(system, text)
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    base = self._fallback.parse_goal(text)
                    base.update({k: v for k, v in parsed.items() if v is not None})
                    base["description"] = text.strip()
                    return base
            except json.JSONDecodeError:
                pass
        return self._fallback.parse_goal(text)

    def explain_incident(self, incident_type: str, evidence: list[str]) -> str:
        system = (
            "You are an HPC training diagnostician. In 2-3 sentences explain the likely root "
            'cause. Reply as JSON: {"explanation": "..."}.'
        )
        raw = self._chat(system, f"Incident: {incident_type}\nEvidence:\n" + "\n".join(evidence))
        if raw:
            try:
                parsed = json.loads(raw)
                explanation = parsed.get("explanation")
                if isinstance(explanation, str) and explanation.strip():
                    return explanation.strip()
            except (json.JSONDecodeError, AttributeError):
                pass
        return self._fallback.explain_incident(incident_type, evidence)


def get_reasoner() -> Reasoner:
    provider = OpenAICompatibleReasoner()
    if provider.available:
        return provider
    return RuleBasedReasoner()
