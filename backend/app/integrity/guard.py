"""Experiment Integrity Guard: tracks all changes, renders diffs, enforces approval."""

from __future__ import annotations

import difflib
from enum import StrEnum
from typing import Any

import yaml

from .classifier import ChangeClass, classify_patch


class IntegrityStatus(StrEnum):
    PRESERVED = "PRESERVED"
    MODIFIED = "MODIFIED"
    UNKNOWN = "UNKNOWN"


class IntegrityGuard:
    """Per-experiment ledger of automatic vs semantic changes."""

    def __init__(self) -> None:
        self.automatic_changes: list[dict[str, Any]] = []
        self.semantic_changes: list[dict[str, Any]] = []
        self.approval_required: list[dict[str, Any]] = []

    def assess(self, original: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        change_class, reasons = classify_patch(original, patch)
        record = {
            "patch": patch,
            "class": change_class.value,
            "reasons": reasons,
            "diff": render_config_diff(original, {**original, **patch}),
        }
        if change_class is ChangeClass.SEMANTICS_PRESERVING:
            self.automatic_changes.append(record)
        else:
            self.semantic_changes.append(record)
            self.approval_required.append(record)
        return record

    @property
    def status(self) -> IntegrityStatus:
        if not self.automatic_changes and not self.semantic_changes:
            return IntegrityStatus.UNKNOWN
        if self.semantic_changes:
            return IntegrityStatus.MODIFIED
        return IntegrityStatus.PRESERVED

    def summary(self) -> dict[str, Any]:
        return {
            "automatic_changes": len(self.automatic_changes),
            "semantic_changes": len(self.semantic_changes),
            "approval_required": len(self.approval_required),
            "integrity": self.status.value,
        }


def render_config_diff(original: dict[str, Any], updated: dict[str, Any]) -> list[str]:
    """Unified-style diff of two configs, one line per change ('- key: old' / '+ key: new')."""
    old_lines = yaml.safe_dump(original, sort_keys=True).splitlines()
    new_lines = yaml.safe_dump(updated, sort_keys=True).splitlines()
    lines: list[str] = []
    for line in difflib.unified_diff(old_lines, new_lines, lineterm="", n=0):
        if not line or line.startswith(("+++", "---", "@@")):
            continue
        if line[0] in "+-":
            lines.append(f"{line[0]} {line[1:]}")
    return lines
