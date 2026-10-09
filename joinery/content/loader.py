"""Load the curriculum from YAML, validate it and render its Markdown.

Content lives in ``content/``:

* ``curriculum.yaml`` lists the modules and the order of their lessons,
* ``lessons/<id>.yaml`` holds one lesson each, and
* ``dialects.yaml`` holds the engine reference and the feature matrix.

See docs/authoring-lessons.md for the format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from markdown_it import MarkdownIt

LEVELS = ("beginner", "intermediate", "advanced")
WIDGETS = ("join-visualizer", "isolation-simulator", "index-lab", "query-journey", "processing-order", "erd")
ENGINES = ("sqlite", "postgres", "mysql", "mssql", "duckdb")
CHECK_MODES = ("result", "state")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MD = MarkdownIt("js-default", {"html": False, "linkify": False, "typographer": False})


class ContentError(ValueError):
    pass


def render(text: str | None) -> str:
    return _MD.render(text or "").strip()


def render_inline(text: str | None) -> str:
    return _MD.renderInline(text or "").strip()


def _require(mapping: dict, key: str, kind: type | tuple, where: str):
    if key not in mapping:
        raise ContentError(f"{where}: missing '{key}'")
    value = mapping[key]
    if not isinstance(value, kind):
        raise ContentError(f"{where}: '{key}' has the wrong type")
    return value


def _slug(value: str, where: str) -> str:
    if not _SLUG.match(value):
        raise ContentError(f"{where}: '{value}' is not a lowercase-hyphenated id")
    return value


@dataclass
class Exercise:
    id: str
    lesson: str
    title: str
    prompt_html: str
    dataset: str
    starter: str
    solution: str
    mode: str
    order_matters: bool
    check_names: bool
    verify: str | None
    hints: list[str]

    def public(self) -> dict:
        return {"id": self.id, "title": self.title, "prompt_html": self.prompt_html, "dataset": self.dataset,
                "starter": self.starter, "mode": self.mode, "order_matters": self.order_matters,
                "hints": [render_inline(h) for h in self.hints]}


@dataclass
class Example:
    id: str
    lesson: str
    dataset: str
    sql: str
    variants: dict[str, str]
    portable: bool
    expect: dict
    setup: str | None

    def sql_for(self, engine: str) -> str | None:
        if engine in self.variants:
            return self.variants[engine]
        if engine == "sqlite" or self.portable:
            return self.sql
        return None


@dataclass
class Content:
    modules: list[dict]
    lessons: dict[str, dict]
    exercises: dict[str, Exercise]
    examples: dict[str, Example]
    dialects: dict
    order: list[str] = field(default_factory=list)

    def curriculum(self) -> list[dict]:
        return self.modules


def _load_yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContentError(f"{path.name}: invalid YAML: {exc}") from exc


def _lesson(path: Path, module_id: str, datasets: set[str], exercises: dict, examples: dict) -> dict:
    raw = _load_yaml(path)
    where = path.name
    if not isinstance(raw, dict):
        raise ContentError(f"{where}: a lesson must be a mapping")
    lesson_id = _slug(_require(raw, "id", str, where), where)
    if path.stem != lesson_id:
        raise ContentError(f"{where}: id '{lesson_id}' must match the file name")
    level = _require(raw, "level", str, where)
    if level not in LEVELS:
        raise ContentError(f"{where}: level must be one of {LEVELS}")
    dataset = _require(raw, "dataset", str, where)
    if dataset not in datasets:
        raise ContentError(f"{where}: unknown dataset '{dataset}'")
    sections = []
    for n, section in enumerate(_require(raw, "sections", list, where), start=1):
        swhere = f"{where} section {n}"
        rendered_examples = []
        for example in section.get("examples", []) or []:
            ex_id = _slug(_require(example, "id", str, swhere), swhere)
            if ex_id in examples:
                raise ContentError(f"{swhere}: duplicate example id '{ex_id}'")
            ex_dataset = example.get("dataset", dataset)
            if ex_dataset not in datasets:
                raise ContentError(f"{swhere}: unknown dataset '{ex_dataset}'")
            variants = example.get("variants") or {}
            for engine in variants:
                if engine not in ENGINES:
                    raise ContentError(f"{swhere}: unknown engine '{engine}' in variants")
            examples[ex_id] = Example(ex_id, lesson_id, ex_dataset, _require(example, "sql", str, swhere).strip(),
                                      {k: v.strip() for k, v in variants.items()}, bool(example.get("portable")),
                                      example.get("expect") or {}, example.get("setup"))
            rendered_examples.append({
                "id": ex_id, "title": example.get("title", ""), "dataset": ex_dataset,
                "sql": example["sql"].strip(), "variants": {k: v.strip() for k, v in variants.items()},
                "portable": bool(example.get("portable")), "note_html": render(example.get("note")),
                "mode": example.get("mode", "run"), "setup": example.get("setup"),
            })
        widget = section.get("widget")
        if widget is not None:
            if not isinstance(widget, dict) or widget.get("type") not in WIDGETS:
                raise ContentError(f"{swhere}: unknown widget {widget!r}")
        sections.append({"title": _require(section, "title", str, swhere), "html": render(section.get("body")),
                         "examples": rendered_examples, "widget": widget})
    public_exercises = []
    for n, item in enumerate(raw.get("exercises", []) or [], start=1):
        ewhere = f"{where} exercise {n}"
        ex_id = _slug(_require(item, "id", str, ewhere), ewhere)
        if ex_id in exercises:
            raise ContentError(f"{ewhere}: duplicate exercise id '{ex_id}'")
        check = item.get("check") or {}
        mode = check.get("mode", "result")
        if mode not in CHECK_MODES:
            raise ContentError(f"{ewhere}: check mode must be one of {CHECK_MODES}")
        if mode == "state" and not check.get("verify"):
            raise ContentError(f"{ewhere}: state checks need a 'verify' query")
        ex_dataset = item.get("dataset", dataset)
        if ex_dataset not in datasets:
            raise ContentError(f"{ewhere}: unknown dataset '{ex_dataset}'")
        exercise = Exercise(
            ex_id, lesson_id, _require(item, "title", str, ewhere), render(_require(item, "prompt", str, ewhere)),
            ex_dataset, str(item.get("starter", "")).strip(), _require(item, "solution", str, ewhere).strip(),
            mode, bool(check.get("order_matters", False)), bool(check.get("check_names", False)),
            check.get("verify"), [str(h) for h in item.get("hints", []) or []])
        exercises[ex_id] = exercise
        public_exercises.append(exercise.public())
    notes = raw.get("dialect_notes") or {}
    for engine in notes:
        if engine not in ENGINES:
            raise ContentError(f"{where}: unknown engine '{engine}' in dialect_notes")
    return {
        "id": lesson_id, "title": _require(raw, "title", str, where), "module": module_id, "level": level,
        "minutes": int(raw.get("minutes", 15)), "dataset": dataset,
        "summary": _require(raw, "summary", str, where).strip(),
        "objectives": [render_inline(o) for o in raw.get("objectives", []) or []],
        "sections": sections, "exercises": public_exercises,
        "dialect_notes": {k: render(v) for k, v in notes.items()},
        "references": [{"title": r["title"], "url": r["url"]} for r in raw.get("references", []) or []],
    }


def load_content(directory: Path, datasets: set[str] | None = None) -> Content:
    if datasets is None:
        from ..datasets import dataset_ids

        datasets = set(dataset_ids())
    curriculum = _load_yaml(directory / "curriculum.yaml")
    modules, lessons, exercises, examples, order = [], {}, {}, {}, []
    for number, module in enumerate(_require(curriculum, "modules", list, "curriculum.yaml"), start=1):
        module_id = _slug(_require(module, "id", str, "curriculum.yaml"), "curriculum.yaml")
        entries = []
        for lesson_id in _require(module, "lessons", list, f"module {module_id}"):
            path = directory / "lessons" / f"{lesson_id}.yaml"
            if not path.exists():
                raise ContentError(f"module {module_id}: lesson file {path.name} is missing")
            lesson = _lesson(path, module_id, datasets, exercises, examples)
            lesson["number"] = f"{number}.{len(entries) + 1}"
            lessons[lesson_id] = lesson
            order.append(lesson_id)
            entries.append({"id": lesson_id, "number": lesson["number"], "title": lesson["title"],
                            "level": lesson["level"], "minutes": lesson["minutes"], "summary": lesson["summary"],
                            "exercises": [e["id"] for e in lesson["exercises"]]})
        modules.append({"id": module_id, "number": number, "title": _require(module, "title", str, module_id),
                        "summary": module.get("summary", ""), "lessons": entries})
    for n, lesson_id in enumerate(order):
        lessons[lesson_id]["previous"] = order[n - 1] if n > 0 else None
        lessons[lesson_id]["next"] = order[n + 1] if n + 1 < len(order) else None
    dialects = _load_yaml(directory / "dialects.yaml") if (directory / "dialects.yaml").exists() else {}
    for feature in dialects.get("features", []) or []:
        for cell in (feature.get("support") or {}).values():
            if isinstance(cell, dict) and cell.get("note"):
                cell["note_html"] = render_inline(cell["note"])
    return Content(modules, lessons, exercises, examples, dialects, order)
