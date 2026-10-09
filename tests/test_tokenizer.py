import unittest

from joinery.sqltools.split import split_statements, statement_texts
from joinery.sqltools.tokenizer import COMMENT, IDENT, NUMBER, OP, PARAM, STRING, WORD, first_keyword, is_blank, significant, tokenize


def kinds(sql, dialect="sqlite"):
    return [(t.kind, t.text) for t in significant(tokenize(sql, dialect))]


class TokenizerTests(unittest.TestCase):
    def test_round_trip_preserves_every_character(self):
        sql = "SELECT a, 'x;y' AS \"q\" -- c\nFROM t /* b */ WHERE n >= 1.5e3;"
        self.assertEqual("".join(t.text for t in tokenize(sql)), sql)

    def test_basic_kinds(self):
        self.assertEqual(
            kinds("select id, 'it''s' from \"order\" where x <> 0x1F"),
            [(WORD, "select"), (WORD, "id"), (OP, ","), (STRING, "'it''s'"), (WORD, "from"),
             (IDENT, '"order"'), (WORD, "where"), (WORD, "x"), (OP, "<>"), (NUMBER, "0x1F")],
        )

    def test_operators_and_params(self):
        toks = kinds("a ->> '$.x' || b :: int = ? AND c = :name AND d = @v AND e = $1")
        self.assertIn((OP, "->>"), toks)
        self.assertIn((OP, "||"), toks)
        self.assertIn((OP, "::"), toks)
        for param in ("?", ":name", "@v", "$1"):
            self.assertIn((PARAM, param), toks)

    def test_numbers_with_underscores_and_decimals(self):
        self.assertEqual([t for k, t in kinds("1_000 .5 3. 2.5E-3") if k == NUMBER], ["1_000", ".5", "3.", "2.5E-3"])

    def test_unterminated_string_is_flagged(self):
        tok = significant(tokenize("SELECT 'oops"))[-1]
        self.assertEqual(tok.kind, STRING)
        self.assertFalse(tok.terminated)

    def test_mysql_rules(self):
        toks = kinds('SELECT "text", `col` # comment\nFROM t WHERE s = \'a\\\'b\'', "mysql")
        self.assertIn((STRING, '"text"'), toks)
        self.assertIn((IDENT, "`col`"), toks)
        self.assertIn((STRING, "'a\\'b'"), toks)
        self.assertNotIn((WORD, "comment"), toks)

    def test_postgres_rules(self):
        toks = kinds("SELECT $tag$ it's; here $tag$, data ? 'k', /* a /* nested */ b */ 1", "postgres")
        self.assertIn((STRING, "$tag$ it's; here $tag$"), toks)
        self.assertIn((OP, "?"), toks)
        self.assertEqual(toks[-1], (NUMBER, "1"))

    def test_mssql_brackets_and_unicode_strings(self):
        toks = kinds("SELECT [order id], N'naïve' FROM [dbo].[t]", "mssql")
        self.assertIn((IDENT, "[order id]"), toks)
        self.assertIn((STRING, "N'naïve'"), toks)

    def test_helpers(self):
        self.assertEqual(first_keyword("  -- hi\n  with x as (select 1) select * from x"), "WITH")
        self.assertTrue(is_blank("  -- only a comment\n /* and another */ "))
        self.assertFalse(is_blank("select 1"))
        self.assertEqual(kinds("-- c")[0:1], [])
        self.assertEqual(tokenize("/* x */")[0].kind, COMMENT)


class SplitterTests(unittest.TestCase):
    def test_splits_on_top_level_semicolons_only(self):
        sql = "SELECT 'a;b'; -- c;\nSELECT \"x;y\" FROM t; /* ; */ SELECT 3"
        self.assertEqual(statement_texts(sql), ["SELECT 'a;b'", "-- c;\nSELECT \"x;y\" FROM t", "/* ; */ SELECT 3"])

    def test_ignores_empty_and_comment_only_statements(self):
        self.assertEqual(statement_texts(";; -- nothing\n ; SELECT 1;  "), ["SELECT 1"])

    def test_trigger_bodies_stay_whole(self):
        sql = (
            "CREATE TRIGGER t AFTER UPDATE ON orders BEGIN\n"
            "  UPDATE audit SET n = CASE WHEN n > 0 THEN n + 1 ELSE 1 END;\n"
            "  INSERT INTO log VALUES (1);\n"
            "END;\nSELECT 1;"
        )
        parts = statement_texts(sql)
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[0].endswith("END"))
        self.assertEqual(parts[1], "SELECT 1")

    def test_positions_point_into_the_source(self):
        sql = "  SELECT 1 ;\n\nSELECT 2"
        for stmt in split_statements(sql):
            self.assertEqual(sql[stmt.start:stmt.end], stmt.text)

    def test_postgres_function_with_dollar_body(self):
        sql = "CREATE FUNCTION f() RETURNS int AS $$ SELECT 1; $$ LANGUAGE sql; SELECT f();"
        self.assertEqual(len(statement_texts(sql, "postgres")), 2)

    def test_plain_begin_is_a_statement(self):
        self.assertEqual(statement_texts("BEGIN; UPDATE t SET a = 1; COMMIT;"), ["BEGIN", "UPDATE t SET a = 1", "COMMIT"])


if __name__ == "__main__":
    unittest.main()
