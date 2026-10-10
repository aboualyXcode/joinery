"""Application services shared by the HTTP API and the command line."""

from __future__ import annotations

import logging
import time

from .config import Settings
from .content import load_content
from .content.explore import load_explore
from .content.loader import Exercise
from .datasets import dataset_ids, get_dataset
from .datasets.build import ensure_built
from .datasets.ddl import DIALECTS, create_script
from .engines import Engine, build_engines
from .grading import compare
from .sandbox import SandboxRunner
from .sqltools.dependencies import dependency_graph, propagate, to_json
from .sqltools.errors import explain_error
from .sqltools.lint import lint
from .sqltools.plans import aliases_for, annotate_bytecode, postgres_tree, sqlite_tree
from .sqltools.split import statement_texts
from .sqltools.stepper import assemble, batches_for, plan_steps
from .sqltools.tokenizer import is_blank

log = logging.getLogger("joinery")


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _preview(result: dict, limit: int = 25) -> dict:
    return {"columns": result["columns"], "rows": result["rows"][:limit], "row_count": result["row_count"]}


class Platform:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.manifest = ensure_built(settings.data_dir)
        self.runner = SandboxRunner(max_concurrency=settings.max_concurrency)
        self.engines = build_engines(settings, self.runner, self.manifest)
        if "sqlite" not in self.engines:
            raise RuntimeError("the SQLite engine must be enabled: exercises are graded on it")
        self.content = load_content(settings.content_dir)
        explore_file = settings.content_dir / "explore.yaml"
        self.explore = load_explore(explore_file, set(dataset_ids())) if explore_file.exists() else {}
        self.schemas, self.checks, self.row_counts = {}, {}, {}
        for dataset_id in dataset_ids():
            dataset = get_dataset(dataset_id)
            self.schemas[dataset_id] = {t.name: t.column_names for t in dataset.tables}
            self.row_counts[dataset_id] = {t.name: len(t.rows) for t in dataset.tables}
            self.checks[dataset_id] = {f"ck_{t.name}_{c.name}": c.check for t in dataset.tables
                                       for c in t.columns if c.check}
        self._expected: dict[tuple[str, str], dict] = {}
        self._exports: dict[tuple[str, str], str] = {}

    # ------------------------------------------------------------------ lookups
    def engine(self, engine_id: str | None) -> Engine:
        engine = self.engines.get(engine_id or "sqlite")
        if engine is None:
            raise ServiceError(f"The engine '{engine_id}' is not enabled on this server.")
        return engine

    def dataset(self, dataset_id: str | None) -> str:
        if dataset_id not in self.schemas:
            raise ServiceError(f"There is no dataset called '{dataset_id}'.", 404)
        return dataset_id

    def meta(self) -> dict:
        return {
            "engines": [engine.describe() for engine in self.engines.values()],
            "datasets": [{"id": d, "title": get_dataset(d).title, "summary": get_dataset(d).summary,
                          "tables": len(self.schemas[d]), "rows": sum(self.row_counts[d].values())}
                         for d in dataset_ids()],
            "limits": {"timeout_ms": self.settings.timeout_ms, "max_rows": self.settings.max_rows,
                       "max_sql_chars": self.settings.max_sql_chars},
        }

    def dataset_detail(self, dataset_id: str) -> dict:
        from .content.loader import render

        schema = get_dataset(self.dataset(dataset_id)).schema()
        schema["description_html"] = render(schema.pop("description"))
        schema["dialects"] = list(DIALECTS)
        return schema

    def export(self, dataset_id: str, dialect: str) -> str:
        self.dataset(dataset_id)
        if dialect not in DIALECTS:
            raise ServiceError(f"Unknown dialect '{dialect}'. Choose one of: {', '.join(DIALECTS)}.")
        key = (dataset_id, dialect)
        if key not in self._exports:
            self._exports[key] = create_script(get_dataset(dataset_id), dialect)
        return self._exports[key]

    # ------------------------------------------------------------------ helpers
    def _explain(self, error: dict | None, sql: str, dataset_id: str) -> dict | None:
        if not error:
            return None
        return {**error, "explanation": explain_error(error, sql, self.schemas[dataset_id], self.checks[dataset_id])}

    def _execute(self, engine: Engine, dataset_id: str, batches: list[dict], timeout_ms: int | None = None) -> dict:
        started = time.perf_counter()
        out = engine.run(dataset_id, batches, timeout_ms=timeout_ms or self.settings.timeout_ms)
        log.info("engine=%s dataset=%s batches=%d ok=%s elapsed_ms=%.1f", engine.id, dataset_id, len(batches),
                 out.get("ok"), (time.perf_counter() - started) * 1000)
        return out

    # ------------------------------------------------------------------ operations
    def run(self, sql: str, dataset_id: str, engine_id: str | None = None) -> dict:
        engine, dataset_id = self.engine(engine_id), self.dataset(dataset_id)
        if is_blank(sql, engine.dialect):
            raise ServiceError("There is no SQL to run.")
        started = time.perf_counter()
        out = self._execute(engine, dataset_id, [{"id": "main", "sql": sql}])
        response = {"engine": engine.id, "engine_version": out.get("engine_version"), "dataset": dataset_id,
                    "statements": [], "skipped": 0, "error": None, "warnings": lint(sql, engine.dialect)}
        if not out.get("ok"):
            response["error"] = self._explain(out.get("error"), sql, dataset_id)
        else:
            batch = out["batches"][0]
            response["skipped"] = batch["skipped"]
            for index, statement in enumerate(batch["statements"]):
                statement["index"] = index
                if statement.get("error"):
                    statement["error"] = self._explain(statement["error"], statement["sql"], dataset_id)
                    if response["error"] is None:
                        response["error"] = {**statement["error"], "statement_index": index}
                response["statements"].append(statement)
        response["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return response

    def explain(self, sql: str, dataset_id: str, engine_id: str | None = None, setup: str | None = None) -> dict:
        engine, dataset_id = self.engine(engine_id), self.dataset(dataset_id)
        statements = statement_texts(sql, engine.dialect)
        if len(statements) != 1:
            raise ServiceError("Explain one statement at a time. Put supporting statements in setup.")
        statement = statements[0]
        batches = [{"id": "setup", "sql": setup}] if setup and not is_blank(setup, engine.dialect) else []
        batches.append({"id": "main", "sql": statement, "split": False, "explain": True, "analyze": True})
        out = self._execute(engine, dataset_id, batches)
        response: dict = {"engine": engine.id, "statement": statement, "tree": [], "advice": [], "plan_text": None,
                          "bytecode": [], "bytecode_summary": None, "metrics": None, "error": None,
                          "setup_error": None}
        if not out.get("ok"):
            response["error"] = self._explain(out.get("error"), statement, dataset_id)
            return response
        if setup and out["batches"][0]["statements"]:
            failed = next((s for s in out["batches"][0]["statements"] if s.get("error")), None)
            if failed:
                response["setup_error"] = self._explain(failed["error"], failed["sql"], dataset_id)
        main = out["batches"][-1]["statements"]
        if not main:
            response["error"] = {"type": "ExplainError", "message": "Nothing was explained.", "explanation": None}
            return response
        entry = main[0]
        if entry.get("error"):
            response["error"] = self._explain(entry["error"], statement, dataset_id)
            return response
        if engine.id == "sqlite":
            response["tree"], response["advice"] = sqlite_tree(entry["plan"], self.row_counts[dataset_id],
                                                               aliases_for(statement))
            response["bytecode"], response["bytecode_summary"] = annotate_bytecode(entry["bytecode"])
        elif entry.get("plan_json"):
            response["tree"], response["advice"] = postgres_tree(entry["plan_json"])
        response["plan_text"] = entry.get("plan_text")
        analysis = entry.get("analyze")
        if analysis:
            response["metrics"] = {key: analysis.get(key) for key in ("row_count", "elapsed_ms", "vm_steps", "changes")}
            if analysis.get("error"):
                response["error"] = self._explain(analysis["error"], statement, dataset_id)
        return response

    def steps(self, sql: str, dataset_id: str, engine_id: str | None = None) -> dict:
        engine, dataset_id = self.engine(engine_id), self.dataset(dataset_id)
        plan = plan_steps(sql, self.schemas[dataset_id], engine.dialect)
        if not plan.supported:
            return assemble(plan, {})
        out = self._execute(engine, dataset_id, batches_for(plan), self.settings.timeout_ms * 2)
        result = assemble(plan, out)
        for stage in result.get("stages", []):
            if stage.get("error"):
                stage["error"] = self._explain(stage["error"], stage["sql"], dataset_id)
        if result.get("error"):
            result["error"] = self._explain(result["error"], sql, dataset_id)
        return result

    def visualize(self, sql: str, dataset_id: str, engine_id: str | None = None) -> dict:
        """Everything the query map draws: dependencies with row counts and
        failure propagation, the logical stages and the physical plan."""
        engine, dataset_id = self.engine(engine_id), self.dataset(dataset_id)
        statements = statement_texts(sql, engine.dialect)
        if len(statements) != 1:
            raise ServiceError("Visualize one statement at a time.")
        statement = statements[0]
        graph = dependency_graph(statement, self.schemas[dataset_id], self.row_counts[dataset_id], engine.dialect)
        dependencies: dict
        if isinstance(graph, dict):
            dependencies = graph
        else:
            batches = []
            for node_id in graph.nodes:
                query = graph.count_query(node_id)
                if query:
                    batches.append({"id": node_id, "sql": query, "split": False})
            if graph.statement == "select":
                batches.append({"id": "query", "sql": f"SELECT count(*) FROM ({graph.sql})", "split": False})
            out = self._execute(engine, dataset_id, batches) if batches else {"ok": True, "batches": []}
            for batch in out.get("batches", []):
                node = graph.nodes.get(batch["id"])
                result = batch["statements"][0] if batch["statements"] else None
                if node is None or result is None:
                    continue
                if result.get("error"):
                    node["status"] = "failed"
                    node["error"] = self._explain(result["error"], statement, dataset_id)
                elif result["rows"]:
                    node["rows"] = result["rows"][0][0]
                    node["work"] = result.get("vm_steps")
            propagate(graph)
            dependencies = to_json(graph)
        try:
            plan = self.explain(statement, dataset_id, engine_id)
        except ServiceError as exc:
            plan = {"error": {"type": "RequestError", "message": exc.message, "explanation": None}}
        return {"engine": engine.id, "dataset": dataset_id, "statement": statement, "dependencies": dependencies,
                "steps": self.steps(statement, dataset_id, engine_id), "plan": plan}

    # ------------------------------------------------------------------ exercises
    def exercise(self, exercise_id: str) -> Exercise:
        exercise = self.content.exercises.get(exercise_id)
        if exercise is None:
            raise ServiceError(f"There is no exercise called '{exercise_id}'.", 404)
        return exercise

    def _batches(self, exercise: Exercise, sql: str) -> list[dict]:
        batches = [{"id": "user", "sql": sql}]
        if exercise.mode == "state":
            batches.append({"id": "verify", "sql": exercise.verify, "split": False})
        return batches

    def _outcome(self, exercise: Exercise, out: dict) -> tuple[dict | None, dict | None]:
        """(result to compare, error) for one run of an exercise."""
        if not out.get("ok"):
            return None, out.get("error")
        user = out["batches"][0]
        failed = next((s for s in user["statements"] if s.get("error")), None)
        if failed:
            return None, {**failed["error"], "sql": failed["sql"]}
        if exercise.mode == "state":
            verify = out["batches"][1]["statements"]
            if not verify or verify[0].get("error"):
                return None, verify[0]["error"] if verify else {"type": "CheckError", "message": "Verification did not run."}
            return verify[0], None
        rows = [s for s in user["statements"] if s["kind"] == "rows"]
        if not rows:
            return None, {"type": "NoResult", "message": "Your SQL did not return any rows. Finish with a SELECT."}
        return rows[-1], None

    def expected(self, exercise: Exercise, engine: Engine) -> dict:
        key = (exercise.id, engine.id)
        if key not in self._expected:
            out = self._execute(engine, exercise.dataset, self._batches(exercise, exercise.solution))
            result, error = self._outcome(exercise, out)
            if error or result is None:
                raise ServiceError(f"The reference solution for {exercise.id} failed: {error}", 500)
            self._expected[key] = result
        return self._expected[key]

    def check(self, exercise_id: str, sql: str, engine_id: str | None = None) -> dict:
        exercise = self.exercise(exercise_id)
        engine = self.engine(engine_id)
        if is_blank(sql, engine.dialect):
            raise ServiceError("Write some SQL first.")
        expected = self.expected(exercise, engine)
        actual, error = self._outcome(exercise, self._execute(engine, exercise.dataset, self._batches(exercise, sql)))
        response: dict = {"exercise": exercise.id, "expected": _preview(expected), "actual": None,
                          "warnings": lint(sql, engine.dialect), "error": None}
        if error:
            explained = self._explain(error, error.get("sql", sql), exercise.dataset)
            summary = "Your query did not return a result." if error.get("type") == "NoResult" else "Your SQL failed."
            response.update(passed=False, summary=summary, details=[error.get("message", "")], hint=None,
                            error=explained)
            return response
        assert actual is not None
        response.update(compare(expected, actual, order_matters=exercise.order_matters,
                                check_names=exercise.check_names))
        response["actual"] = _preview(actual)
        if response["passed"] and exercise.plan_searched and engine.id == "sqlite":
            response.update(self._check_plan(exercise, engine, sql))
        return response

    def _check_plan(self, exercise: Exercise, engine: Engine, sql: str) -> dict:
        """Performance exercises also require that named tables are reached through an index."""
        statements = statement_texts(sql, engine.dialect)
        last = statements[-1]
        batches = [{"id": "setup", "sql": ";\n".join(statements[:-1])}] if len(statements) > 1 else []
        batches.append({"id": "plan", "sql": last, "split": False, "explain": True})
        out = self._execute(engine, exercise.dataset, batches)
        entries = out["batches"][-1]["statements"] if out.get("ok") else []
        if not entries or entries[0].get("error"):
            return {"passed": False, "summary": "The result is right, but the query plan could not be checked.",
                    "details": [], "hint": None}
        tree, _advice = sqlite_tree(entries[0]["plan"], self.row_counts[exercise.dataset], aliases_for(last))
        nodes, stack = [], list(tree)
        while stack:
            node = stack.pop()
            nodes.append(node)
            stack.extend(node["children"])
        for table in exercise.plan_searched:
            touching = [n for n in nodes if n["table"] == table]
            slow = [n for n in touching if n["kind"] != "search"]  # a covering-index SCAN still reads every entry
            if slow or not touching:
                return {"passed": False,
                        "summary": f"The result is right, but the plan still reads {table} without a usable index.",
                        "details": [n["label"] for n in nodes],
                        "hint": f"Make sure {table} is reached with SEARCH ... USING INDEX: check the Plan tab."}
        return {"summary": "Correct, and the plan uses an index as intended.",
                "plan": [n["label"] for n in nodes]}

    def solution(self, exercise_id: str) -> dict:
        exercise = self.exercise(exercise_id)
        return {"exercise": exercise.id, "solution": exercise.solution}
