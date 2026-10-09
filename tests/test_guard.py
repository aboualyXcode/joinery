import unittest

from joinery.engines.guard import check_statement


class GuardTests(unittest.TestCase):
    def assert_allowed(self, sql, dialect):
        self.assertIsNone(check_statement(sql, dialect), f"{dialect}: {sql}")

    def assert_blocked(self, sql, dialect):
        self.assertIsNotNone(check_statement(sql, dialect), f"{dialect}: {sql}")

    def test_ordinary_sql_is_allowed_everywhere(self):
        for dialect in ("postgres", "mysql", "mssql"):
            for sql in ("SELECT * FROM orders WHERE id = 1",
                        "WITH x AS (SELECT 1 AS n) SELECT n FROM x",
                        "UPDATE orders SET status = 'paid' WHERE id = 3",
                        "DELETE FROM reviews WHERE rating < 2",
                        "INSERT INTO teams (name, city) VALUES ('Larks', 'Leeds')",
                        "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"):
                self.assert_allowed(sql, dialect)

    def test_transaction_control_is_refused(self):
        for dialect in ("postgres", "mysql", "mssql"):
            for sql in ("COMMIT", "BEGIN", "ROLLBACK", "START TRANSACTION", "commit work"):
                self.assert_blocked(sql, dialect)

    def test_savepoints_are_allowed(self):
        self.assert_allowed("ROLLBACK TO SAVEPOINT before_update", "postgres")
        self.assert_allowed("ROLLBACK TO before_update", "mysql")
        self.assert_allowed("SAVE TRANSACTION before_update", "mssql")
        self.assert_allowed("ROLLBACK TRANSACTION before_update", "mssql")
        self.assert_blocked("ROLLBACK TRANSACTION", "mssql")

    def test_privilege_and_server_changes_are_refused(self):
        self.assert_blocked("CREATE ROLE admin SUPERUSER", "postgres")
        self.assert_blocked("ALTER USER sandbox WITH PASSWORD 'x'", "postgres")
        self.assert_blocked("GRANT ALL ON orders TO public", "postgres")
        self.assert_blocked("CREATE EXTENSION dblink", "postgres")
        self.assert_blocked("ALTER SYSTEM SET work_mem = '1GB'", "postgres")
        self.assert_blocked("CREATE LOGIN x WITH PASSWORD = 'y'", "mssql")
        self.assert_blocked("DROP DATABASE joinery_shop", "mysql")

    def test_file_and_code_execution_is_refused(self):
        self.assert_blocked("COPY orders TO '/tmp/out.csv'", "postgres")
        self.assert_blocked("SELECT pg_read_file('/etc/passwd')", "postgres")
        self.assert_blocked("DO $$ BEGIN PERFORM 1; END $$", "postgres")
        self.assert_blocked("SELECT * FROM orders INTO OUTFILE '/tmp/x'", "mysql")
        self.assert_blocked("SELECT LOAD_FILE('/etc/passwd')", "mysql")
        self.assert_blocked("EXEC xp_cmdshell 'dir'", "mssql")
        self.assert_blocked("SELECT * FROM OPENROWSET('SQLNCLI', 'x', 'y')", "mssql")
        self.assert_blocked("EXECUTE ('COMMIT')", "mssql")

    def test_session_settings(self):
        self.assert_allowed("SET LOCAL enable_seqscan = off", "postgres")
        self.assert_blocked("SET LOCAL statement_timeout = 0", "postgres")
        self.assert_blocked("SET ROLE postgres", "postgres")
        self.assert_blocked("SET SESSION AUTHORIZATION postgres", "postgres")
        self.assert_blocked("SET autocommit = 1", "mysql")
        self.assert_allowed("SET @total = 0", "mysql")
        self.assert_blocked("SET NOCOUNT ON", "mssql")

    def test_mysql_ddl_is_limited_to_temporary_tables(self):
        self.assert_blocked("CREATE TABLE t (a INT)", "mysql")
        self.assert_blocked("ALTER TABLE orders ADD COLUMN x INT", "mysql")
        self.assert_allowed("CREATE TEMPORARY TABLE t (a INT)", "mysql")
        self.assert_allowed("DROP TEMPORARY TABLE t", "mysql")
        self.assert_allowed("CREATE TABLE t (a int)", "postgres")
        self.assert_allowed("CREATE INDEX idx ON orders (customer_id)", "postgres")

    def test_keywords_inside_strings_do_not_trigger(self):
        self.assert_allowed("SELECT 'COMMIT; DROP DATABASE x' AS note", "postgres")
        self.assert_allowed("SELECT 'pg_read_file' AS fn", "postgres")


if __name__ == "__main__":
    unittest.main()
