"""Load the sample datasets into a server engine and create the sandbox login.

Experimental: used by the engines CI workflow and the Compose ``engines``
profile. Run it with an administrator connection; Joinery itself then
connects as ``joinery_sandbox``, which can only read and write the dataset
tables. See docs/engines.md.
"""

from __future__ import annotations

from .datasets import dataset_ids, get_dataset
from .datasets.ddl import create_script
from .sqltools.split import statement_texts

SANDBOX_ROLE = "joinery_sandbox"


def _statements(dataset_id: str, dialect: str) -> list[str]:
    return statement_texts(create_script(get_dataset(dataset_id), dialect), dialect)


def provision_postgres(admin_dsn: str, password: str, datasets: list[str]) -> list[str]:
    import psycopg
    from psycopg import sql

    log = []
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (SANDBOX_ROLE,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
                                "CONNECTION LIMIT 50").format(sql.Identifier(SANDBOX_ROLE), sql.Literal(password)))
            log.append(f"created role {SANDBOX_ROLE}")
        role = sql.Identifier(SANDBOX_ROLE)
        cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '10s'").format(role))
        cur.execute(sql.SQL("ALTER ROLE {} SET temp_file_limit = '256MB'").format(role))
        cur.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        for dataset_id in datasets:
            schema = sql.Identifier(dataset_id)
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(schema))
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
            cur.execute(sql.SQL("SET search_path TO {}").format(schema))
            for statement in _statements(dataset_id, "postgres"):
                cur.execute(statement)
            cur.execute("ANALYZE")
            cur.execute(sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {}").format(schema, role))
            cur.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}").format(schema, role))
            cur.execute(sql.SQL("GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {} TO {}").format(schema, role))
            log.append(f"loaded {dataset_id}")
    return log


def provision_mysql(admin_dsn: str, password: str, datasets: list[str]) -> list[str]:
    import pymysql

    from .engines.server import _mysql_params

    log = []
    conn = pymysql.connect(autocommit=True, charset="utf8mb4", **_mysql_params(admin_dsn))
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE USER IF NOT EXISTS '{SANDBOX_ROLE}'@'%%' IDENTIFIED BY %s", (password,))
            for dataset_id in datasets:
                database = f"joinery_{dataset_id}"
                cur.execute(f"DROP DATABASE IF EXISTS `{database}`")
                cur.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
                cur.execute(f"USE `{database}`")
                for statement in _statements(dataset_id, "mysql"):
                    cur.execute(statement)
                cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE TEMPORARY TABLES ON `{database}`.* "
                            f"TO '{SANDBOX_ROLE}'@'%'")
                log.append(f"loaded {dataset_id}")
    finally:
        conn.close()
    return log


def provision_mssql(admin_dsn: str, password: str, datasets: list[str]) -> list[str]:
    import mssql_python

    log = []
    secret = password.replace("'", "''")
    conn = mssql_python.connect(admin_dsn)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(f"IF SUSER_ID('{SANDBOX_ROLE}') IS NULL CREATE LOGIN {SANDBOX_ROLE} WITH PASSWORD = '{secret}', "
                    "CHECK_POLICY = OFF")
        for dataset_id in datasets:
            database = f"joinery_{dataset_id}"
            cur.execute(f"DROP DATABASE IF EXISTS {database}")
            cur.execute(f"CREATE DATABASE {database}")
            cur.execute(f"USE {database}")
            for statement in _statements(dataset_id, "mssql"):
                cur.execute(statement)
            cur.execute(f"CREATE USER {SANDBOX_ROLE} FOR LOGIN {SANDBOX_ROLE}")
            cur.execute(f"ALTER ROLE db_datareader ADD MEMBER {SANDBOX_ROLE}")
            cur.execute(f"ALTER ROLE db_datawriter ADD MEMBER {SANDBOX_ROLE}")
            cur.execute(f"GRANT SHOWPLAN TO {SANDBOX_ROLE}")
            log.append(f"loaded {dataset_id}")
    finally:
        conn.close()
    return log


PROVISIONERS = {"postgres": provision_postgres, "mysql": provision_mysql, "mssql": provision_mssql}


def provision(engine: str, admin_dsn: str, password: str, datasets: list[str] | None = None) -> list[str]:
    if engine not in PROVISIONERS:
        raise ValueError(f"cannot provision {engine}; choose one of {', '.join(PROVISIONERS)}")
    return PROVISIONERS[engine](admin_dsn, password, datasets or dataset_ids())
