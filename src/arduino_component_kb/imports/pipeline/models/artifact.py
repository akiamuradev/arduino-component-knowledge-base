"""Immutable source payload passed from acquisition to extraction."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from arduino_component_kb.imports.pipeline.models.provenance import SourceArtifactMetadata


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    metadata: SourceArtifactMetadata
    content: bytes

    def __post_init__(self) -> None:
        if len(self.content) != self.metadata.byte_length:
            raise ValueError("source_artifact_length_mismatch")
        if sha256(self.content).hexdigest() != self.metadata.content_sha256:
            raise ValueError("source_artifact_digest_mismatch")
