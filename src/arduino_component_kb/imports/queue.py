"""Queue contract for durable import jobs."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class ImportQueue(Protocol):
    def enqueue(self, job_id: UUID) -> None: ...


class DramatiqImportQueue:
    def enqueue(self, job_id: UUID) -> None:
        from arduino_component_kb.imports.tasks import process_import

        process_import.send(str(job_id))
