"""Engine-neutral description of a sample dataset: tables, columns, keys and rows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

LOGICAL_TYPES = ("integer", "bigint", "decimal", "varchar", "text", "boolean", "date", "timestamp", "json")
_TYPE = re.compile(r"^(?P<base>[a-z]+)(?:\((?P<args>[0-9, ]+)\))?$")


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    identity: bool = False  # surrogate key that new rows may omit
    unique: bool = False
    references: str | None = None  # "table.column"
    check: str | None = None  # portable boolean expression
    default: str | None = None  # SQL literal
    doc: str = ""

    def __post_init__(self) -> None:
        match = _TYPE.match(self.type)
        if not match or match.group("base") not in LOGICAL_TYPES:
            raise ValueError(f"column {self.name}: unknown type {self.type!r}")

    @property
    def base_type(self) -> str:
        return self.type.split("(", 1)[0]

    @property
    def type_args(self) -> tuple[int, ...]:
        match = _TYPE.match(self.type)
        args = match.group("args") if match else None
        return tuple(int(part) for part in args.split(",")) if args else ()

    @property
    def ref_table(self) -> str | None:
        return self.references.split(".", 1)[0] if self.references else None

    @property
    def ref_column(self) -> str | None:
        return self.references.split(".", 1)[1] if self.references else None


@dataclass(frozen=True, slots=True)
class Index:
    name: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(slots=True)
class Table:
    name: str
    doc: str
    columns: list[Column]
    rows: list[tuple]
    indexes: list[Index] = field(default_factory=list)
    position: tuple[int, int] = (0, 0)  # top-left corner in the ERD canvas

    def __post_init__(self) -> None:
        width = len(self.columns)
        for row in self.rows:
            if len(row) != width:
                raise ValueError(f"{self.name}: row has {len(row)} values, expected {width}")

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def primary_key(self) -> list[str]:
        return [c.name for c in self.columns if c.primary_key]

    def column(self, name: str) -> Column:
        for col in self.columns:
            if col.name == name:
                return col
        raise KeyError(f"{self.name} has no column {name}")


@dataclass(slots=True)
class Dataset:
    id: str
    title: str
    summary: str
    description: str
    tables: list[Table]

    def table(self, name: str) -> Table:
        for table in self.tables:
            if table.name == name:
                return table
        raise KeyError(f"dataset {self.id} has no table {name}")

    def foreign_keys(self) -> list[tuple[str, str, str, str]]:
        return [
            (t.name, c.name, c.ref_table or "", c.ref_column or "")
            for t in self.tables
            for c in t.columns
            if c.references
        ]

    def ordered_tables(self) -> list[Table]:
        """Tables sorted so that every referenced table comes first."""
        remaining = {t.name: t for t in self.tables}
        ordered: list[Table] = []
        while remaining:
            progressed = False
            for name, table in list(remaining.items()):
                deps = {c.ref_table for c in table.columns if c.ref_table and c.ref_table != name}
                if not deps & remaining.keys():
                    ordered.append(table)
                    del remaining[name]
                    progressed = True
            if not progressed:
                raise ValueError(f"circular foreign keys in {self.id}: {sorted(remaining)}")
        return ordered

    def schema(self) -> dict:
        """JSON-friendly schema description for the API and the client."""
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "description": self.description,
            "tables": [
                {
                    "name": t.name,
                    "doc": t.doc,
                    "row_count": len(t.rows),
                    "position": list(t.position),
                    "columns": [
                        {
                            "name": c.name,
                            "type": c.type,
                            "nullable": c.nullable and not c.primary_key,
                            "primary_key": c.primary_key,
                            "unique": c.unique,
                            "references": c.references,
                            "doc": c.doc,
                        }
                        for c in t.columns
                    ],
                    "indexes": [
                        {"name": i.name, "columns": list(i.columns), "unique": i.unique} for i in t.indexes
                    ],
                }
                for t in self.tables
            ],
        }
