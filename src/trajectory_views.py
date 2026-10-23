"""Compatibility facade for the original trajectory-view import path."""

from src.trajectory.views import (
    AGENT_FIELDS,
    FORBIDDEN_AGENT_FIELDS,
    ORACLE_FIELDS,
    build_agent_view,
    build_oracle_view,
)

__all__ = [
    "AGENT_FIELDS",
    "FORBIDDEN_AGENT_FIELDS",
    "ORACLE_FIELDS",
    "build_agent_view",
    "build_oracle_view",
]
