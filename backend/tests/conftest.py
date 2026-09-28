"""Shared pytest fixtures: isolate data dir, put backend on sys.path."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("AETHER_DATA_DIR", str(Path(__file__).parent / "_testdata"))


@pytest.fixture()
def tmp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "exp-test"
    ws.mkdir()
    return ws
