"""Refuse statements that could escape a server engine's per-run transaction.

SQLite and DuckDB runs execute in a throwaway process, so nothing a learner
does can persist. Server engines (PostgreSQL, MySQL, SQL Server) keep the
datasets in a shared database instead. Every run happens inside a
transaction that Joinery always rolls back, under a role that can only read
and write the dataset tables. This guard is the second layer: it refuses
statements that would end that transaction, change identity or privileges,
touch the filesystem, or (on MySQL) commit implicitly.

The guard is lexical and deliberately conservative. Database permissions
remain the primary control.
"""

from __future__ import annotations

from ..sqltools.tokenizer import WORD, significant, tokenize

_COMMON = {
    "BEGIN": "Transactions are managed by Joinery: each run is one transaction that is rolled back.",
    "START": "Transactions are managed by Joinery: each run is one transaction that is rolled back.",
    "COMMIT": "Committing is disabled on shared engines so the sample data stays pristine.",
    "END": "Committing is disabled on shared engines so the sample data stays pristine.",
    "ABORT": "Transactions are managed by Joinery.",
    "GRANT": "Changing privileges is disabled.",
    "REVOKE": "Changing privileges is disabled.",
    "DENY": "Changing privileges is disabled.",
    "COPY": "COPY can read or write files and is disabled.",
    "LOAD": "Loading files or libraries is disabled.",
    "CALL": "Calling procedures is disabled on shared engines.",
    "LISTEN": "Notifications are disabled.",
    "NOTIFY": "Notifications are disabled.",
    "UNLISTEN": "Notifications are disabled.",
    "VACUUM": "Maintenance commands are disabled on shared engines.",
    "CHECKPOINT": "Maintenance commands are disabled on shared engines.",
    "CLUSTER": "Maintenance commands are disabled on shared engines.",
    "RESET": "Changing session settings is disabled.",
    "DISCARD": "Changing session settings is disabled.",
    "PREPARE": "Prepared transactions and statements are disabled.",
    "EXECUTE": "Dynamic SQL is disabled on shared engines.",
    "EXEC": "Dynamic SQL is disabled on shared engines.",
    "DO": "Anonymous code blocks are disabled on shared engines.",
}
_DIALECT_FIRST_WORDS = {
    "mysql": {
        "LOCK": "Table locks are disabled.", "UNLOCK": "Table locks are disabled.",
        "HANDLER": "HANDLER is disabled.", "FLUSH": "FLUSH is disabled.", "KILL": "KILL is disabled.",
        "SHUTDOWN": "SHUTDOWN is disabled.", "INSTALL": "Plugins are disabled.", "UNINSTALL": "Plugins are disabled.",
        "XA": "Distributed transactions are disabled.", "RENAME": "On MySQL, DDL commits implicitly and is disabled.",
        "TRUNCATE": "On MySQL, TRUNCATE commits implicitly and is disabled.",
    },
    "mssql": {
        "GO": "GO is a client batch separator, not SQL. Separate statements with semicolons.",
        "USE": "Switching databases is disabled.", "BACKUP": "BACKUP is disabled.", "RESTORE": "RESTORE is disabled.",
        "DBCC": "DBCC is disabled.", "SHUTDOWN": "SHUTDOWN is disabled.", "KILL": "KILL is disabled.",
        "RECONFIGURE": "RECONFIGURE is disabled.", "BULK": "BULK INSERT reads files and is disabled.",
    },
}
# Planner and transaction settings that are safe and useful to change for one run.
_SAFE_LOCAL_SETTINGS = {"RANDOM_PAGE_COST", "SEQ_PAGE_COST", "CPU_TUPLE_COST", "JIT", "PLAN_CACHE_MODE",
                        "TRANSACTION", "DATESTYLE", "TIMEZONE", "INTERVALSTYLE", "EXTRA_FLOAT_DIGITS"}
_PRIVILEGED_OBJECTS = {"ROLE", "USER", "LOGIN", "DATABASE", "SCHEMA", "EXTENSION", "TABLESPACE", "SERVER",
                       "SYSTEM", "PUBLICATION", "SUBSCRIPTION", "LANGUAGE", "EVENT", "CERTIFICATE", "CREDENTIAL"}
_DANGEROUS_WORDS = {
    "postgres": {"PG_READ_FILE", "PG_READ_BINARY_FILE", "PG_LS_DIR", "PG_STAT_FILE", "LO_IMPORT", "LO_EXPORT",
                 "DBLINK", "DBLINK_EXEC", "SET_CONFIG", "PG_TERMINATE_BACKEND", "PG_CANCEL_BACKEND",
                 "PG_RELOAD_CONF", "PG_ROTATE_LOGFILE"},
    "mysql": {"OUTFILE", "DUMPFILE", "LOAD_FILE", "SLEEP"},
    "mssql": {"OPENROWSET", "OPENDATASOURCE", "OPENQUERY", "OPENXML", "XP_CMDSHELL", "SP_CONFIGURE",
              "SP_EXECUTESQL", "SP_OACREATE", "SP_ADDLOGIN", "SP_ADDSRVROLEMEMBER"},
}


def check_statement(sql: str, dialect: str) -> str | None:
    """Return a reason when the statement must not run, else None."""
    words = significant(tokenize(sql, dialect))
    if not words:
        return None
    upper = [t.upper if t.kind == WORD else t.text for t in words]
    first = upper[0]
    second = upper[1] if len(upper) > 1 else ""

    if first == "ROLLBACK":
        if "TO" in upper[1:3] or (dialect == "mssql" and second in ("TRAN", "TRANSACTION") and len(upper) > 2):
            return None  # rolling back to a savepoint keeps Joinery's transaction open
        return "Rolling back the whole run is not needed: Joinery always rolls back for you."
    if first == "SET":
        if second == "TRANSACTION":
            return None  # isolation level for this run's transaction
        third = upper[2] if len(upper) > 2 else ""
        if dialect == "postgres" and second == "LOCAL" and (third.startswith("ENABLE_") or third in _SAFE_LOCAL_SETTINGS):
            return None
        if dialect == "mysql" and second.startswith("@") and not second.startswith("@@"):
            return None
        if dialect == "mssql" and second.startswith("@") and not second.startswith("@@"):
            return None
        return "Changing session settings is disabled on shared engines."
    reason = _COMMON.get(first)
    if reason:
        return reason
    dialect_reason = _DIALECT_FIRST_WORDS.get(dialect, {}).get(first)
    if dialect_reason:
        return dialect_reason
    if first in ("CREATE", "ALTER", "DROP"):
        objects = set(upper[1:5])
        if objects & _PRIVILEGED_OBJECTS:
            return f"{first} {second} is disabled: it changes the server rather than your sample data."
        if dialect == "mysql" and not (
            (first == "CREATE" and second == "TEMPORARY") or (first == "DROP" and second == "TEMPORARY")
        ):
            return "MySQL commits DDL implicitly, so only CREATE/DROP TEMPORARY TABLE is allowed here."
    if first == "ALTER" and second == "SYSTEM":
        return "ALTER SYSTEM is disabled."
    if first == "IMPORT" or (first == "SECURITY" and second == "LABEL"):
        return "This command is disabled on shared engines."
    dangerous = _DANGEROUS_WORDS.get(dialect, set())
    for token in upper:
        if token in dangerous or (dialect == "mssql" and token.startswith(("XP_", "SP_"))):
            return f"{token.lower()} is disabled on shared engines."
    if dialect == "mssql" and first in ("EXEC", "EXECUTE"):
        return "Dynamic SQL is disabled on shared engines."
    return None
