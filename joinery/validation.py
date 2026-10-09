"""Run every lesson example and exercise against an engine.

Used by ``python -m joinery validate``, the test suite and CI. For each
example it checks that the SQL runs (or fails with the expected error) and
returns the expected number of rows. For each exercise it checks that the
reference solution passes and that the starter code does not.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .service import Platform
from .sqltools.tokenizer import is_blank


def _check_example(platform: Platform, example, engine_id: str) -> str | None:
    sql = example.sql_for(engine_id)
    batches = [{"id": "setup", "sql": example.setup}] if example.setup else []
    batches.append({"id": "main", "sql": sql})
    out = platform.engine(engine_id).run(example.dataset, batches, timeout_ms=platform.settings.timeout_ms * 2)
    if not out.get("ok"):
        return f"run failed: {out.get('error')}"
    for batch in out["batches"][:-1]:
        failed = next((s for s in batch["statements"] if s.get("error")), None)
        if failed:
            return f"setup failed: {failed['error']['message']}"
    statements = out["batches"][-1]["statements"]
    if not statements:
        return "nothing ran"
    last = statements[-1]
    expected_error = example.expect.get("error")
    if expected_error:
        if not last.get("error"):
            return f"expected an error containing {expected_error!r}, but it succeeded"
        if expected_error.lower() not in last["error"]["message"].lower():
            return f"expected an error containing {expected_error!r}, got {last['error']['message']!r}"
        return None
    failed = next((s for s in statements if s.get("error")), None)
    if failed:
        return f"{failed['error']['type']}: {failed['error']['message']}"
    if "rows" in example.expect and last["row_count"] != example.expect["rows"]:
        return f"expected {example.expect['rows']} rows, got {last['row_count']}"
    return None


def _check_exercise(platform: Platform, exercise, engine_id: str) -> list[str]:
    problems = []
    result = platform.check(exercise.id, exercise.solution, engine_id)
    if not result.get("passed"):
        problems.append(f"the solution does not pass: {result.get('summary')} {result.get('details')}")
    if exercise.starter and not is_blank(exercise.starter):
        starter = platform.check(exercise.id, exercise.starter, engine_id)
        if starter.get("passed"):
            problems.append("the starter code already passes")
    return problems


def validate(platform: Platform, engine_id: str = "sqlite", lesson: str | None = None, jobs: int = 4) -> dict:
    examples = [e for e in platform.content.examples.values()
                if (lesson is None or e.lesson == lesson) and e.sql_for(engine_id) is not None]
    exercises = [x for x in platform.content.exercises.values() if lesson is None or x.lesson == lesson]
    failures: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        example_results = list(pool.map(lambda e: (e, _check_example(platform, e, engine_id)), examples))
        exercise_results = (list(pool.map(lambda x: (x, _check_exercise(platform, x, engine_id)), exercises))
                            if engine_id == "sqlite" else [])
    for example, problem in example_results:
        if problem:
            failures.append({"kind": "example", "id": example.id, "lesson": example.lesson, "message": problem})
    for exercise, problems in exercise_results:
        for problem in problems:
            failures.append({"kind": "exercise", "id": exercise.id, "lesson": exercise.lesson, "message": problem})
    skipped = sum(1 for e in platform.content.examples.values()
                  if (lesson is None or e.lesson == lesson) and e.sql_for(engine_id) is None)
    return {"engine": engine_id, "examples": len(examples), "exercises": len(exercise_results),
            "skipped": skipped, "failures": failures}
