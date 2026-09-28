"""Skill package endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..skills.registry import registry

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
def list_skills() -> list[dict]:
    return [skill.summary() for skill in registry.all()]


@router.get("/{name}")
def get_skill(name: str) -> dict:
    skill = registry.get(name)
    if skill is None:
        raise HTTPException(404, "skill not found")
    return {**skill.summary(), "skill_md": skill.skill_md}
