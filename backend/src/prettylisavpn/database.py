"""Shared SQLAlchemy declarative metadata used by models and Alembic."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for persistent models."""
