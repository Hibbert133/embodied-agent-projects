"""Provenance contract for figures, videos, and trajectory visualizations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ArtifactKind(str, Enum):
    FIGURE = "figure"
    VIDEO = "video"
    TRAJECTORY = "trajectory"


@dataclass(frozen=True)
class ArtifactManifestEntry:
    artifact_id: str
    kind: ArtifactKind
    path: Path
    source_result_path: Path
    selection_rule: str

    def __post_init__(self) -> None:
        if not self.artifact_id.strip() or not self.selection_rule.strip():
            raise ValueError("visual artifact requires identity and an explicit selection rule")
        if self.path == self.source_result_path:
            raise ValueError("visual artifact and source result must be distinct paths")
