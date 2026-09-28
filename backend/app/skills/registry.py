"""Skill registry: loaded once at startup, shared read-only."""

from __future__ import annotations

from pathlib import Path

from ..core.config import settings
from .loader import SkillPackage, load_skills


class SkillRegistry:
    def __init__(self, skills_dir: Path | None = None) -> None:
        self._skills: dict[str, SkillPackage] = {}
        for package in load_skills(skills_dir or settings.skills_dir):
            self._skills[package.name] = package

    def all(self) -> list[SkillPackage]:
        return list(self._skills.values())

    def get(self, name: str) -> SkillPackage | None:
        return self._skills.get(name)


registry = SkillRegistry()
