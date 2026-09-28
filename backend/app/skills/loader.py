"""Skill package loader.

A skill package is a directory with skill.yaml + SKILL.md (+ policies/, tools/,
detectors/, recovery/, schemas/, evals/). Loading is declarative: the registry
exposes capabilities and policies to the API and the agent; the orchestrator
implements the behavior under the contract's permission gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REQUIRED_KEYS = {"name", "version", "capabilities"}


class SkillPackage:
    def __init__(self, root: Path, meta: dict[str, Any], skill_md: str) -> None:
        self.root = root
        self.meta = meta
        self.skill_md = skill_md

    @property
    def name(self) -> str:
        return str(self.meta["name"])

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.meta["name"],
            "version": self.meta.get("version"),
            "display_name": self.meta.get("display_name", self.meta["name"]),
            "description": self.meta.get("description", ""),
            "capabilities": self.meta.get("capabilities", []),
            "permissions": self.meta.get("permissions", {}),
            "detectors": self.meta.get("detectors", []),
            "recovery_strategies": self.meta.get("recovery_strategies", []),
            "eval_cases": self.meta.get("evals", []),
            "path": str(self.root),
            "installed": True,
        }


def load_skill(root: Path) -> SkillPackage:
    skill_yaml = root / "skill.yaml"
    skill_md = root / "SKILL.md"
    if not skill_yaml.is_file():
        raise ValueError(f"{root}: missing skill.yaml")
    meta = yaml.safe_load(skill_yaml.read_text(encoding="utf-8"))
    missing = _REQUIRED_KEYS - set(meta)
    if missing:
        raise ValueError(f"{root}: skill.yaml missing keys {sorted(missing)}")
    return SkillPackage(root, meta, skill_md.read_text(encoding="utf-8") if skill_md.is_file() else "")


def load_skills(skills_dir: Path) -> list[SkillPackage]:
    packages: list[SkillPackage] = []
    if not skills_dir.is_dir():
        return packages
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / "skill.yaml").is_file():
            packages.append(load_skill(child))
    return packages
