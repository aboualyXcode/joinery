"""Record API responses so a static copy of the client can replay them.

The published preview on GitHub Pages has no server. Its client fetches
``snapshots/get/<path>.json`` for GET requests and
``snapshots/post/<sha1>.json`` for POST requests, where the hash is taken
over the same canonical string that ``snapshot_key`` builds. Everything the
preview shows was recorded from the real engine by ``record``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def snapshot_key(path: str, body: dict) -> str:
    canonical = "\n".join([
        path,
        str(body.get("dataset") or "shop"),
        str(body.get("engine") or "sqlite"),
        str(body.get("setup") or ""),
        str(body.get("sql") or ""),
    ])
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()  # noqa: S324 - a cache key, not security


def _with_setup(setup: str | None, sql: str) -> str:
    if not setup:
        return sql
    head = setup.strip()
    if head.endswith(";"):
        head = head[:-1]
    return f"{head};\n{sql}"


def record(app, out: Path, *, include_examples: bool = True) -> dict:
    client = app.test_client()
    platform = app.extensions["joinery"]
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}

    def save(relative: str, status: int, body) -> None:
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps({"status": status, "body": body}, separators=(",", ":"))
        target.write_text(data, encoding="utf-8")
        written[relative] = len(data)

    def get(path: str, extra: dict | None = None) -> None:
        response = client.get(path)
        body = response.get_json()
        if extra:
            body.update(extra)
        save(f"get/{path[len('/api/'):]}.json", response.status_code, body)

    def post(path: str, body: dict) -> None:
        relative = f"post/{snapshot_key(path, body)}.json"
        if relative not in written:
            response = client.post(path, json=body)
            save(relative, response.status_code, response.get_json())

    get("/api/meta", {"static": True})
    for path in ("/api/curriculum", "/api/dialects", "/api/explore"):
        get(path)
    for dataset_id in platform.schemas:
        get(f"/api/datasets/{dataset_id}")
    for lesson_id in platform.content.lessons:
        get(f"/api/lessons/{lesson_id}")
    for exercise_id in platform.content.exercises:
        get(f"/api/exercises/{exercise_id}/solution")

    def workbench(sql: str, dataset: str, setup: str | None = None) -> None:
        post("/api/run", {"sql": _with_setup(setup, sql), "dataset": dataset, "engine": "sqlite"})
        post("/api/steps", {"sql": sql, "dataset": dataset, "engine": "sqlite"})
        post("/api/explain", {"sql": sql, "dataset": dataset, "engine": "sqlite", "setup": setup})
        post("/api/visualize", {"sql": sql, "dataset": dataset, "engine": "sqlite"})

    explore = platform.explore
    for failure in explore["failures"]:
        if failure.get("demo"):
            post("/api/run", {"sql": failure["demo"]["sql"], "dataset": failure["demo"]["dataset"]})
        compare = failure.get("compare")
        if compare:
            for side in (compare["slow"], compare["fast"]):
                body = {"sql": side["sql"], "dataset": compare["dataset"], "setup": side.get("setup")}
                post("/api/run" if failure["kind"] == "wrong" else "/api/explain", body)
    for query in explore["queries"]:
        post("/api/visualize", {"sql": query["sql"], "dataset": query["dataset"]})
    presets = explore["presets"]
    post("/api/steps", {"sql": presets["journey"], "dataset": "shop"})
    post("/api/explain", {"sql": presets["journey"], "dataset": "shop"})
    sample = "\n".join(f"{keyword} {body}" for keyword, body, _step in presets["processing"])
    post("/api/steps", {"sql": sample, "dataset": "shop"})
    for dataset_id, sql in presets["playground"].items():
        workbench(sql, dataset_id)
    lab = presets["join_lab"]
    for sql in [lab["players"], lab["teams"], *lab["sql"].values()]:
        post("/api/run", {"sql": sql, "dataset": "joinlab"})
    for preset in presets["index_lab"]:
        cols = preset["columns"]
        post("/api/explain", {"sql": preset["sql"], "dataset": "shop"})
        for combo in [[c] for c in cols] + [cols[:2], cols[1::-1]]:
            setup = f"CREATE INDEX lab_index ON {preset['table']} ({', '.join(combo)})"
            post("/api/explain", {"sql": preset["sql"], "dataset": "shop", "setup": setup})
    if include_examples:
        for lesson in platform.content.lessons.values():
            for section in lesson["sections"]:
                for example in section["examples"]:
                    workbench(example["sql"], example["dataset"], example["setup"])
    return {"files": len(written), "bytes": sum(written.values())}
