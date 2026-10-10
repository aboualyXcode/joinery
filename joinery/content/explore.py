"""Load and validate the Explore data: the engine map, flows, failures,
symptom fans and query presets in content/explore.yaml."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

LAYERS = ("client", "compiler", "execution", "storage", "guard")
KINDS = ("error", "hang", "slow", "wrong")
STATION_W, STATION_H = 160, 44


class ExploreError(ValueError):
    pass


def _edge_points(edge: dict, stations: dict, steps: int = 60) -> list[tuple[float, float]]:
    a, b = stations[edge["from"]], stations[edge["to"]]
    points = []
    for n in range(steps + 1):
        t = n / steps
        if edge.get("bend"):
            cx, cy = edge["bend"]
            x = (1 - t) ** 2 * a["x"] + 2 * (1 - t) * t * cx + t * t * b["x"]
            y = (1 - t) ** 2 * a["y"] + 2 * (1 - t) * t * cy + t * t * b["y"]
        else:
            x = a["x"] + (b["x"] - a["x"]) * t
            y = a["y"] + (b["y"] - a["y"]) * t
        points.append((x, y))
    return points


def geometry_problems(stations: dict, edges: list[dict], margin: float = 4) -> list[str]:
    """Stations must not overlap and no connection may run through a station."""
    problems = []
    ids = list(stations)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if abs(stations[a]["x"] - stations[b]["x"]) < STATION_W + margin and \
                    abs(stations[a]["y"] - stations[b]["y"]) < STATION_H + margin:
                problems.append(f"stations {a} and {b} overlap")
    for edge in edges:
        for sid, s in stations.items():
            if sid in (edge["from"], edge["to"]):
                continue
            for x, y in _edge_points(edge, stations):
                if abs(x - s["x"]) <= STATION_W / 2 + margin and abs(y - s["y"]) <= STATION_H / 2 + margin:
                    problems.append(f"edge {edge['from']}-{edge['to']} runs through {sid}")
                    break
    return problems


def load_explore(path: Path, datasets: set[str]) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    stations = {}
    for s in data["stations"]:
        if s["id"] in stations:
            raise ExploreError(f"duplicate station {s['id']}")
        if s["layer"] not in LAYERS:
            raise ExploreError(f"station {s['id']}: unknown layer {s['layer']}")
        stations[s["id"]] = s
    edges = []
    for raw in data["edges"]:
        edge = {"from": raw[0], "to": raw[1], "bend": None} if isinstance(raw, list) else \
            {"from": raw["from"], "to": raw["to"], "bend": raw.get("bend")}
        for end in (edge["from"], edge["to"]):
            if end not in stations:
                raise ExploreError(f"edge refers to unknown station {end}")
        edges.append(edge)
    data["edges"] = edges
    pairs = {frozenset((e["from"], e["to"])) for e in edges}

    def connected(a: str, b: str, where: str) -> None:
        if frozenset((a, b)) not in pairs:
            raise ExploreError(f"{where}: {a} and {b} are not connected on the map")

    problems = geometry_problems(stations, edges)
    if problems:
        raise ExploreError("; ".join(problems))
    for flow in data["flows"]:
        for step in flow["steps"]:
            if step["at"] not in stations:
                raise ExploreError(f"flow {flow['id']}: unknown station {step['at']}")
            if step.get("from"):
                connected(step["from"], step["at"], f"flow {flow['id']}")
    failures = {}
    for failure in data["failures"]:
        fid = failure["id"]
        if fid in failures:
            raise ExploreError(f"duplicate failure {fid}")
        if failure["kind"] not in KINDS:
            raise ExploreError(f"failure {fid}: unknown kind {failure['kind']}")
        path_ = failure["path"]
        if path_[0] != failure["origin"]:
            raise ExploreError(f"failure {fid}: the path must start at the origin")
        for a, b in zip(path_, path_[1:], strict=False):
            connected(a, b, f"failure {fid}")
        for a, b in failure.get("knock", []):
            connected(a, b, f"failure {fid} knock-on")
        for pattern in failure.get("patterns", []):
            if "(?<" in pattern:
                raise ExploreError(f"failure {fid}: lookbehind is not portable to the browser")
            re.compile(pattern, re.IGNORECASE)
        for item in ("demo",):
            if failure.get(item) and failure[item]["dataset"] not in datasets:
                raise ExploreError(f"failure {fid}: unknown dataset")
        if failure.get("compare") and failure["compare"]["dataset"] not in datasets:
            raise ExploreError(f"failure {fid}: unknown dataset")
        failures[fid] = failure
    for symptom in data["symptoms"]:
        for fid in symptom["failures"]:
            if fid not in failures:
                raise ExploreError(f"symptom {symptom['id']}: unknown failure {fid}")
    ids = set()
    for query in data["queries"]:
        if query["id"] in ids or query["dataset"] not in datasets:
            raise ExploreError(f"query {query['id']} is duplicated or uses an unknown dataset")
        ids.add(query["id"])
    return data


def match_failure(explore: dict, message: str) -> str | None:
    for failure in explore["failures"]:
        for pattern in failure.get("patterns", []):
            if re.search(pattern, message, re.IGNORECASE):
                return failure["id"]
    return None
