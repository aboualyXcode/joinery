"""The interface every engine implements.

An engine executes *batches*. A batch is a script (split into statements)
or a single statement, optionally explained instead of executed. Every
engine returns the same JSON-friendly shape, so the service layer (runs,
plans, the stepper and grading) does not care which engine ran the SQL.
"""

from __future__ import annotations


class Engine:
    id = "engine"
    name = "Engine"
    dialect = "sqlite"
    experimental = False

    def available(self) -> bool:
        return True

    def version(self) -> str:
        return "unknown"

    def run(self, dataset_id: str, batches: list[dict], *, timeout_ms: int) -> dict:
        raise NotImplementedError

    def describe(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "dialect": self.dialect,
            "version": self.version(),
            "experimental": self.experimental,
            "available": self.available(),
        }


def failure(kind: str, message: str) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message, "code": None}}
