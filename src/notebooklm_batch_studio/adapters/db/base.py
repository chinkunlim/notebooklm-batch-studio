"""Declarative base shared by every ORM model."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for ORM models; `Base.metadata` is what Alembic compares against."""
