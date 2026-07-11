"""Nested transaction helpers for paper trading persistence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


@contextmanager
def transaction_scope(session: Session) -> Iterator[None]:
    """Begin a transaction or nested savepoint when already in a transaction."""
    if session.in_transaction():
        with session.begin_nested():
            yield
    else:
        with session.begin():
            yield
