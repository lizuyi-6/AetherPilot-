"""SQLite via SQLAlchemy sync engine guarded by a re-entrant lock.

The workload is low-concurrency (single machine operator console), so a sync
engine with a lock is simpler and more predictable than an async driver.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import settings
from .models import Base

_engine = None
_session_factory: sessionmaker[Session] | None = None
_lock = threading.RLock()


def init_db(db_path=None) -> None:
    global _engine, _session_factory
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(_engine)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    with _lock:
        session = _session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
