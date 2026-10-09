import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from joinery.datasets import BUILDERS, get_dataset
from joinery.datasets.build import ensure_built, sqlite_image
from joinery.datasets.ddl import DIALECTS, column_type, create_script, literal, quote_string
from joinery.datasets.model import Column


def digest(dataset):
    h = hashlib.sha256()
    for table in dataset.tables:
        h.update(table.name.encode())
        for row in table.rows:
            h.update(repr(row).encode())
    return h.hexdigest()


class DatasetTests(unittest.TestCase):
    def test_generation_is_deterministic(self):
        for dataset_id, build in BUILDERS.items():
            with self.subTest(dataset=dataset_id):
                self.assertEqual(digest(build()), digest(build()))

    def test_images_respect_every_constraint(self):
        for dataset_id in BUILDERS:
            with self.subTest(dataset=dataset_id):
                con = sqlite3.connect(":memory:")
                con.deserialize(sqlite_image(get_dataset(dataset_id)))
                self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                for table in get_dataset(dataset_id).tables:
                    count = con.execute(f"SELECT count(*) FROM {table.name}").fetchone()[0]
                    self.assertEqual(count, len(table.rows), table.name)

    def test_primary_keys_are_unique(self):
        for dataset_id in BUILDERS:
            for table in get_dataset(dataset_id).tables:
                if not table.primary_key:
                    continue  # raw staging tables have no key on purpose
                key = [table.column_names.index(c) for c in table.primary_key]
                values = [tuple(row[i] for i in key) for row in table.rows]
                self.assertEqual(len(values), len(set(values)), f"{dataset_id}.{table.name}")

    def test_tables_are_ordered_by_dependency(self):
        order = [t.name for t in get_dataset("shop").ordered_tables()]
        self.assertLess(order.index("customers"), order.index("orders"))
        self.assertLess(order.index("orders"), order.index("order_items"))
        self.assertLess(order.index("categories"), order.index("products"))

    def test_designed_teaching_cases_exist(self):
        shop = get_dataset("shop")
        ordered = {row[1] for row in shop.table("orders").rows}
        self.assertTrue(any(row[0] not in ordered for row in shop.table("customers").rows))
        sold = {row[2] for row in shop.table("order_items").rows}
        self.assertTrue(any(row[0] not in sold for row in shop.table("products").rows))
        players = get_dataset("joinlab").table("players").rows
        self.assertEqual(sum(1 for row in players if row[2] is None), 2)

    def test_schema_description(self):
        schema = get_dataset("shop").schema()
        orders = next(t for t in schema["tables"] if t["name"] == "orders")
        customer_id = next(c for c in orders["columns"] if c["name"] == "customer_id")
        self.assertEqual(customer_id["references"], "customers.id")
        self.assertEqual(orders["row_count"], len(get_dataset("shop").table("orders").rows))


class ExportTests(unittest.TestCase):
    def test_every_dialect_renders_every_table(self):
        for dataset_id in BUILDERS:
            dataset = get_dataset(dataset_id)
            for dialect in DIALECTS:
                script = create_script(dataset, dialect)
                for table in dataset.tables:
                    self.assertIn(f"CREATE TABLE {table.name} (", script, f"{dataset_id}/{dialect}")

    def test_sqlite_export_round_trips(self):
        con = sqlite3.connect(":memory:")
        con.executescript(create_script(get_dataset("pipeline"), "sqlite"))
        for table in get_dataset("pipeline").tables:
            self.assertEqual(con.execute(f"SELECT count(*) FROM {table.name}").fetchone()[0], len(table.rows))

    def test_literals_are_escaped_per_dialect(self):
        self.assertEqual(quote_string("O'Brien", "postgres"), "'O''Brien'")
        self.assertEqual(quote_string("a\\b", "mysql"), "'a\\\\b'")
        self.assertEqual(quote_string("naïve", "mssql"), "N'naïve'")
        flag = Column("f", "boolean")
        self.assertEqual(literal(True, flag, "postgres"), "TRUE")
        self.assertEqual(literal(True, flag, "mssql"), "1")
        self.assertEqual(literal(12.5, Column("p", "decimal(10,2)"), "mysql"), "12.50")
        self.assertEqual(literal(None, flag, "sqlite"), "NULL")

    def test_type_mapping(self):
        self.assertEqual(column_type(Column("e", "varchar(120)"), "mssql"), "NVARCHAR(120)")
        self.assertEqual(column_type(Column("p", "decimal(10,2)"), "postgres"), "numeric(10,2)")
        self.assertEqual(column_type(Column("j", "json"), "postgres"), "jsonb")
        self.assertEqual(column_type(Column("t", "timestamp"), "mysql"), "DATETIME")

    def test_identity_columns(self):
        script = create_script(get_dataset("joinlab"), "duckdb")
        self.assertIn("CREATE SEQUENCE teams_id_seq START 5;", script)
        self.assertIn("SET IDENTITY_INSERT teams ON;", create_script(get_dataset("joinlab"), "mssql"))


class BuildTests(unittest.TestCase):
    def test_ensure_built_is_idempotent(self):
        directory = Path(tempfile.mkdtemp())
        first = ensure_built(directory)
        stamp = (directory / "shop.sqlite").stat().st_mtime_ns
        second = ensure_built(directory)
        self.assertEqual(first, second)
        self.assertEqual(stamp, (directory / "shop.sqlite").stat().st_mtime_ns)
        self.assertEqual(set(first["datasets"]), set(BUILDERS))


if __name__ == "__main__":
    unittest.main()
