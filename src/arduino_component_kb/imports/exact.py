"""Stable exact-deduplication keys for parser results."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from arduino_component_kb.catalog.normalization import normalize_exact_identity
from arduino_component_kb.imports.domain import ParsedComponent


@dataclass(frozen=True, slots=True)
class ExactKeys:
    canonical_url: str
    source_item_id: str
    normalized_manufacturer: str | None
    normalized_model: str | None

    @classmethod
    def from_parsed(cls, parsed: ParsedComponent) -> ExactKeys:
        return cls(
            canonical_url=parsed.canonical_url,
            source_item_id=parsed.source_item_id,
            normalized_manufacturer=normalize_exact_identity(parsed.manufacturer),
            normalized_model=normalize_exact_identity(parsed.model),
        )

    @property
    def lock_name(self) -> str:
        if self.normalized_manufacturer and self.normalized_model:
            material = "\x00".join(
                ("manufacturer-model", self.normalized_manufacturer, self.normalized_model)
            )
        else:
            material = "\x00".join(("source", self.canonical_url, self.source_item_id))
        return f"ackb:import:exact:{sha256(material.encode()).hexdigest()}"
