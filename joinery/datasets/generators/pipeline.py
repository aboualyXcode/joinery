"""Raw staging data for ETL, data quality and incremental-load lessons.

Two batches ("loads") arrived from an upstream export: one on 2026-05-01 and
one on 2026-06-01. The raw tables keep every value as text, including
inconsistent casing, stray spaces, three date formats, comma decimals,
'n/a' amounts, blank currencies and duplicates. Load 1 has already been
cleaned into dim_customer and fact_orders using the rules in ``clean_order``.
"""

from __future__ import annotations

import random
import re
from datetime import date, timedelta

from ..model import Column as C
from ..model import Dataset, Table
from .common import email_for, person, weighted

SEED = 909
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T")
_AMOUNT = re.compile(r"^[0-9][0-9.]*$")


def _email(rng: random.Random, email: str) -> str | None:
    if rng.random() < 0.03:
        return None
    return weighted(rng, [(email, 70), (email.title() + " ", 15), (email.upper(), 10), ("  " + email, 5)])


def _date(rng: random.Random, value: date) -> str:
    return weighted(rng, [
        (value.isoformat(), 70),
        (value.strftime("%d/%m/%Y"), 15),
        (value.isoformat() + "T10:15:00Z", 10),
        (rng.choice(["", "unknown"]), 5),
    ])


def _amount(rng: random.Random, value: float) -> str:
    text = f"{value:.2f}"
    return weighted(rng, [(text, 80), (f" {text} ", 7), (text.replace(".", ","), 5), ("$" + text, 4), ("n/a", 4)])


def _status(rng: random.Random, status: str) -> str:
    return weighted(rng, [(status, 70), (status.title(), 15), (status.upper() + " ", 10), (" " + status, 5)])


def clean_order(row: tuple) -> tuple | None:
    """The cleaning rules the lessons express in SQL. Returns None for rejects."""
    _load, _row_no, ref, email, raw_date, raw_amount, raw_currency, raw_status = row
    email = (email or "").strip().lower()
    text = (raw_date or "").strip()
    if _ISO.match(text):
        order_date = text
    elif _DMY.match(text):
        order_date = f"{text[6:10]}-{text[3:5]}-{text[0:2]}"
    elif _ISO_TS.match(text):
        order_date = text[:10]
    else:
        order_date = None
    amount_text = (raw_amount or "").strip().replace("$", "").replace(",", ".")
    currency = (raw_currency or "").strip().upper()
    if not email or not order_date or not _AMOUNT.match(amount_text) or amount_text.count(".") > 1:
        return None
    if currency not in ("USD", "EUR"):
        return None
    return (ref, email, order_date, round(float(amount_text), 2), currency, (raw_status or "").strip().lower())


def build() -> Dataset:
    rng = random.Random(SEED)
    people = []
    for n in range(1, 48):
        first, last = person(rng)
        people.append((email_for(first, last, n, "example.org"), f"{first} {last}",
                       weighted(rng, [("US", 40), ("GB", 20), ("DE", 15), ("NL", 10), ("FR", 15)])))

    def raw_customer(load_id: int, row_no: int, person_row: tuple, updated: str) -> tuple:
        email, name, country = person_row
        country_text = weighted(rng, [(country, 70), (country.lower(), 15), (" " + country, 10), (country + " ", 5)])
        return (load_id, row_no, weighted(rng, [(email, 75), (email.upper(), 15), (" " + email, 10)]),
                name, country_text, updated)

    raw_customers = [raw_customer(1, i + 1, people[i], "2026-04-28 10:00:00") for i in range(40)]
    load2 = []
    for i in range(30):
        load2.append(people[i])
    moves = ["GB", "NL", "DE", "US", "FR", "SE", "IE", "ES"]
    for k, i in enumerate(range(30, 38)):
        email, name, country = people[i]
        if k % 2 == 0:
            load2.append((email, name, moves[k] if moves[k] != country else "SE"))
        else:
            load2.append((email, name.split()[0] + " " + rng.choice(["Okafor", "Lindqvist", "Moreau", "Reyes"]), country))
    for i in range(40, 47):
        load2.append(people[i])
    raw_customers += [raw_customer(2, n + 1, row, "2026-05-29 09:30:00") for n, row in enumerate(load2)]

    raw_orders = []
    known = [p[0] for p in people[:40]]
    later = [p[0] for p in people[:47]]

    def order_row(load_id: int, row_no: int, ref: str, email: str, when: date, amount: float, status: str) -> tuple:
        return (load_id, row_no, ref, _email(rng, email), _date(rng, when), _amount(rng, amount),
                weighted(rng, [("USD", 70), ("usd", 10), ("EUR", 10), ("", 5), (" eur", 5)]), _status(rng, status))

    first_batch = []
    for n in range(150):
        ref = f"CL-{10001 + n}"
        status = weighted(rng, [("shipped", 30), ("delivered", 60), ("cancelled", 10)])
        row = order_row(1, n + 1, ref, rng.choice(known), date(2026, 4, 1) + timedelta(days=rng.randint(0, 29)),
                        round(rng.uniform(8, 180), 2), status)
        first_batch.append(row)
    raw_orders += first_batch

    row_no = 0
    second_batch = []
    for n in range(140):
        row_no += 1
        ref = f"CL-{10151 + n}"
        status = weighted(rng, [("shipped", 45), ("delivered", 45), ("cancelled", 10)])
        second_batch.append(order_row(2, row_no, ref, rng.choice(later), date(2026, 5, 1) + timedelta(days=rng.randint(0, 30)),
                                      round(rng.uniform(8, 180), 2), status))
    for old in rng.sample(first_batch, 20):
        row_no += 1
        status = "delivered" if old[7].strip().lower() == "shipped" else old[7].strip().lower()
        second_batch.append((2, row_no, old[2], old[3], old[4], old[5], old[6], status))
    for dup in rng.sample(second_batch[:140], 4):
        row_no += 1
        second_batch.append((2, row_no) + dup[2:])
    raw_orders += second_batch

    latest: dict[str, tuple] = {}
    for row in first_batch:
        latest[row[2]] = row
    facts = []
    for ref in sorted(latest):
        cleaned = clean_order(latest[ref])
        if cleaned:
            facts.append(cleaned + (1,))
    dims = [(i + 1, row[2].strip().lower(), row[3].strip(), row[4].strip().upper(), "2026-05-01", None, True)
            for i, row in enumerate(raw_customers[:40])]
    runs = [
        (1, "customers", "2026-05-01 06:00:00", "2026-05-01 06:00:09", "success", 40, 40, 1),
        (2, "orders", "2026-05-01 06:01:00", "2026-05-01 06:01:31", "success", 150, len(facts), 1),
        (3, "orders", "2026-06-01 06:01:00", "2026-06-01 06:01:04", "failed", len(second_batch), 0, None),
    ]

    text = "varchar(60)"
    tables = [
        Table("raw_customers", "Customer rows exactly as the upstream export sent them.", [
            C("load_id", "integer", nullable=False), C("row_no", "integer", nullable=False),
            C("email", text), C("full_name", text), C("country", text), C("updated_at", text),
        ], raw_customers, [], (20, 20)),
        Table("raw_orders", "Order rows exactly as received: every value is text.", [
            C("load_id", "integer", nullable=False), C("row_no", "integer", nullable=False),
            C("order_ref", text), C("customer_email", text), C("order_date", text),
            C("amount", text), C("currency", text), C("status", text),
        ], raw_orders, [], (20, 230)),
        Table("dim_customer", "Customer dimension with history (slowly changing dimension, type 2).", [
            C("customer_key", "integer", primary_key=True, identity=True),
            C("email", "varchar(120)", nullable=False),
            C("full_name", "varchar(120)", nullable=False),
            C("country", "varchar(2)", nullable=False),
            C("valid_from", "date", nullable=False),
            C("valid_to", "date"),
            C("is_current", "boolean", nullable=False),
        ], dims, [], (330, 20)),
        Table("fact_orders", "Clean, deduplicated orders. Load 1 is already here.", [
            C("order_ref", "varchar(20)", primary_key=True),
            C("customer_email", "varchar(120)", nullable=False),
            C("order_date", "date", nullable=False),
            C("amount", "decimal(10,2)", nullable=False, check="amount >= 0"),
            C("currency", "varchar(3)", nullable=False, check="currency IN ('USD', 'EUR')"),
            C("status", "varchar(12)", nullable=False),
            C("load_id", "integer", nullable=False),
        ], facts, [], (330, 230)),
        Table("etl_runs", "One row per pipeline run. last_load_id is the watermark.", [
            C("run_id", "integer", primary_key=True, identity=True),
            C("pipeline", "varchar(20)", nullable=False),
            C("started_at", "timestamp", nullable=False),
            C("finished_at", "timestamp"),
            C("status", "varchar(10)", nullable=False, check="status IN ('running', 'success', 'failed')"),
            C("rows_read", "integer"),
            C("rows_loaded", "integer"),
            C("last_load_id", "integer"),
        ], runs, [], (620, 20)),
    ]
    return Dataset(
        id="pipeline",
        title="Staging pipeline",
        summary="Raw text exports with duplicates and bad values, a type 2 customer dimension and a fact table.",
        description=(
            "Two upstream exports arrived on 2026-05-01 (load 1) and 2026-06-01 (load 2). The `raw_*` "
            "tables store every value as text, warts and all: mixed casing, stray spaces, three date "
            "formats, comma decimals, `n/a` amounts, blank currencies and duplicate rows. Load 1 is "
            "already cleaned into `dim_customer` and `fact_orders`; the run that tried load 2 failed."
        ),
        tables=tables,
    )
