"""Tidewater Bank: a fictional retail bank.

Customers hold checking, savings and credit accounts. A year of transactions
includes payroll, card spending, cash withdrawals, transfers between a
customer's own accounts, fees and interest, plus a few bursts of suspicious
overseas card activity. Amounts are signed: money in is positive.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from ..model import Column as C
from ..model import Dataset, Index, Table
from .common import CITIES, between, day, daytime, email_for, money, person, ts, weighted

SEED = 1807
START = datetime(2025, 7, 1)
SNAPSHOT = datetime(2026, 7, 1)

MERCHANTS = [
    ("Harbor Grocers", "groceries", "US"), ("Greenleaf Market", "groceries", "US"),
    ("Daily Basket", "groceries", "US"), ("Corner Pantry", "groceries", "US"),
    ("FreshField Foods", "groceries", "US"), ("Riverside Co-op", "groceries", "US"),
    ("Saffron Table", "dining", "US"), ("Blue Door Bistro", "dining", "US"), ("Noodle Lab", "dining", "US"),
    ("Taco Garage", "dining", "US"), ("Pizzeria Sole", "dining", "US"), ("Burger Yard", "dining", "US"),
    ("Bluefin Air", "travel", "US"), ("Northline Rail", "travel", "US"), ("Seabird Hotels", "travel", "US"),
    ("Wayfarer Car Hire", "travel", "US"), ("Skyport Parking", "travel", "US"),
    ("Beacon Fuel", "fuel", "US"), ("Roadstar Petrol", "fuel", "US"), ("Quickfill Station", "fuel", "US"),
    ("Circuit House", "electronics", "US"), ("Pixel Planet", "electronics", "US"),
    ("Voltline Electronics", "electronics", "US"),
    ("Tidewater Power", "utilities", "US"), ("AquaFlow Water", "utilities", "US"),
    ("Linkup Broadband", "utilities", "US"), ("Signal Mobile", "utilities", "US"),
    ("Starlight Cinemas", "entertainment", "US"), ("Streamhaus", "entertainment", "US"),
    ("Arcadia Games", "entertainment", "US"),
    ("Wellpoint Pharmacy", "health", "US"), ("Pulse Fitness", "health", "US"), ("Harbor Dental", "health", "US"),
    ("Threadline Apparel", "shopping", "US"), ("Homestead Living", "shopping", "US"),
    ("Bookworm & Co", "shopping", "US"), ("Paws & Claws Pets", "shopping", "US"),
    ("Copperleaf Tea & Coffee", "coffee", "US"), ("Daily Grind Cafe", "coffee", "US"),
    ("Lumiere Electronique", "electronics", "FR"), ("Tokyo Gadget Hub", "electronics", "JP"),
    ("Hotel Mitte Berlin", "travel", "DE"), ("Lisbon Tram Tours", "travel", "PT"),
    ("Riad Stay Marrakech", "travel", "MA"), ("Cafe de Flore Bleu", "dining", "FR"),
]
SPEND = {
    "groceries": (15, 140, 30), "dining": (12, 90, 22), "travel": (80, 900, 4), "fuel": (30, 90, 10),
    "electronics": (25, 1200, 3), "utilities": (40, 180, 6), "entertainment": (8, 60, 9),
    "health": (10, 200, 5), "shopping": (15, 250, 9), "coffee": (4, 35, 14),
}
EMPLOYERS = ["Harborview Logistics", "Sunbeam Health", "Kestrel Software", "Meridian Schools", "Oakline Foods"]


def build() -> Dataset:
    rng = random.Random(SEED)
    domestic = [(i, m) for i, m in enumerate(MERCHANTS, start=1) if m[2] == "US"]
    overseas = [(i, m) for i, m in enumerate(MERCHANTS, start=1) if m[2] != "US"]
    by_category: dict[str, list[int]] = {}
    for mid, (_name, category, _country) in domestic:
        by_category.setdefault(category, []).append(mid)

    customers, accounts, txns = [], [], []
    for cid in range(1, 121):
        first, last = person(rng)
        segment = weighted(rng, [("retail", 75), ("premier", 18), ("business", 7)])
        joined = between(rng, datetime(2016, 1, 1), datetime(2025, 5, 1))
        customers.append((cid, f"{first} {last}", email_for(first, last, cid, "mail.example"),
                          segment, day(joined), rng.choice(CITIES["US"])))
        kinds = ["checking"] + (["savings"] if rng.random() < 0.5 else []) + (["credit"] if rng.random() < 0.35 else [])
        for kind in kinds:
            opened = between(rng, max(joined, datetime(2019, 1, 1)), datetime(2025, 6, 1))
            currency = "USD" if kind == "credit" else weighted(rng, [("USD", 90), ("EUR", 6), ("GBP", 4)])
            limit = float(rng.choice([1000, 2500, 5000, 7500, 10000, 15000])) if kind == "credit" else None
            closed = between(rng, datetime(2025, 10, 1), datetime(2026, 5, 1)) if rng.random() < 0.04 else None
            accounts.append([len(accounts) + 1, cid, kind, currency, day(opened), day(closed) if closed else None,
                             limit, segment])

    def add(account_id, moment, amount, kind, description, merchant=None, counterparty=None):
        txns.append([account_id, moment, money(amount), kind, merchant, counterparty, description])

    for acc in accounts:
        aid, cid, kind, _cur, _opened, closed, limit, segment = acc
        end = datetime.fromisoformat(closed) if closed else SNAPSHOT
        if kind in ("checking", "savings"):
            add(aid, START + timedelta(hours=rng.randint(8, 12)), rng.randint(500, 20000), "deposit", "Opening balance")
        savings = next((a[0] for a in accounts if a[1] == cid and a[2] == "savings"), None)
        employer = rng.choice(EMPLOYERS)
        month = START
        while month < end:
            nxt = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
            if kind == "checking":
                if segment == "business":
                    for _ in range(rng.randint(2, 5)):
                        add(aid, daytime(rng, between(rng, month, nxt - timedelta(days=1))),
                            rng.randint(1500, 9000), "deposit", "Client payment")
                else:
                    pay = rng.randint(2800, 5200) if segment == "retail" else rng.randint(7000, 12000)
                    add(aid, month.replace(day=25, hour=6), pay, "deposit", f"Payroll {employer}")
                spends = {"retail": (8, 14), "premier": (10, 18), "business": (6, 10)}[segment]
                for _ in range(rng.randint(*spends)):
                    category = weighted(rng, [(c, w) for c, (_lo, _hi, w) in SPEND.items()])
                    lo, hi, _w = SPEND[category]
                    merchant = rng.choice(by_category[category])
                    amount = -(rng.uniform(lo, hi) if category != "electronics" or rng.random() < 0.2 else rng.uniform(lo, 120))
                    add(aid, daytime(rng, between(rng, month, nxt - timedelta(hours=1))), amount, "card",
                        f"Card purchase {MERCHANTS[merchant - 1][0]}", merchant)
                for _ in range(weighted(rng, [(0, 40), (1, 40), (2, 20)])):
                    add(aid, daytime(rng, between(rng, month, nxt - timedelta(hours=1))),
                        -float(rng.choice([40, 60, 80, 100, 200, 300])), "withdrawal", "ATM withdrawal")
                if savings and rng.random() < 0.85:
                    moment = month.replace(day=26, hour=9, minute=rng.randint(0, 59))
                    amount = float(rng.choice([100, 200, 250, 500, 750, 1000, 1500]))
                    add(aid, moment, -amount, "transfer_out", "Transfer to savings", counterparty=savings)
                    add(savings, moment, amount, "transfer_in", "Transfer from checking", counterparty=aid)
                if rng.random() < 0.03:
                    add(aid, daytime(rng, between(rng, month, nxt - timedelta(hours=1))), -35, "fee", "Overdraft fee")
            elif kind == "savings":
                add(aid, nxt - timedelta(hours=2), rng.uniform(2, 40), "interest", "Interest earned")
            else:
                spent = 0.0
                for _ in range(rng.randint(5, 12)):
                    category = weighted(rng, [(c, w) for c, (_lo, _hi, w) in SPEND.items()])
                    lo, hi, _w = SPEND[category]
                    amount = rng.uniform(lo, min(hi, (limit or 1000) / 4))
                    spent += amount
                    merchant = rng.choice(by_category[category])
                    add(aid, daytime(rng, between(rng, month, nxt - timedelta(hours=1))), -amount, "card",
                        f"Card purchase {MERCHANTS[merchant - 1][0]}", merchant)
                repay = spent if rng.random() < 0.7 else spent * rng.uniform(0.2, 0.6)
                if nxt + timedelta(days=5) < end:
                    add(aid, nxt + timedelta(days=5, hours=10), repay, "transfer_in", "Card payment received")
            month = nxt

    # Three checking accounts show a burst of overseas card activity.
    checking = [a for a in accounts if a[2] == "checking" and not a[5]]
    for acc in rng.sample(checking, 3):
        moment = daytime(rng, between(rng, datetime(2026, 2, 1), datetime(2026, 6, 20)))
        for _ in range(rng.randint(6, 9)):
            mid, merchant = rng.choice(overseas)
            moment += timedelta(seconds=rng.randint(40, 120))
            add(acc[0], moment, -rng.uniform(150, 1400), "card", f"Card purchase {merchant[0]}", mid)

    txns = [t for t in txns if t[1] < SNAPSHOT]
    txns.sort(key=lambda t: (t[1], t[0], t[3]))
    transactions = [(tid, t[0], ts(t[1]), t[2], t[3], t[4], t[5], t[6]) for tid, t in enumerate(txns, start=1)]

    rates = []
    eur, gbp = 1.085, 1.27
    moment = START
    while moment < SNAPSHOT:
        if moment.weekday() < 5:
            eur = round(max(1.0, eur + rng.gauss(0, 0.004)), 6)
            gbp = round(max(1.15, gbp + rng.gauss(0, 0.005)), 6)
            rates.append((day(moment), "EUR", eur))
            rates.append((day(moment), "GBP", gbp))
        moment += timedelta(days=1)

    merchants = [(mid, name, category, country) for mid, (name, category, country) in enumerate(MERCHANTS, start=1)]
    account_rows = [tuple(a[:7]) for a in accounts]
    kinds = "'deposit', 'withdrawal', 'card', 'transfer_in', 'transfer_out', 'fee', 'interest'"
    tables = [
        Table("customers", "Bank customers.", [
            C("id", "integer", primary_key=True, identity=True),
            C("full_name", "varchar(120)", nullable=False),
            C("email", "varchar(120)", nullable=False, unique=True),
            C("segment", "varchar(10)", nullable=False, check="segment IN ('retail', 'premier', 'business')"),
            C("joined_on", "date", nullable=False),
            C("city", "varchar(60)", nullable=False),
        ], customers, [], (20, 20)),
        Table("accounts", "Checking, savings and credit accounts.", [
            C("id", "integer", primary_key=True, identity=True),
            C("customer_id", "integer", nullable=False, references="customers.id"),
            C("kind", "varchar(10)", nullable=False, check="kind IN ('checking', 'savings', 'credit')"),
            C("currency", "varchar(3)", nullable=False),
            C("opened_on", "date", nullable=False),
            C("closed_on", "date"),
            C("credit_limit", "decimal(12,2)", doc="Only for credit accounts."),
        ], account_rows, [Index("idx_accounts_customer", ("customer_id",))], (290, 20)),
        Table("merchants", "Card merchants and their category.", [
            C("id", "integer", primary_key=True, identity=True),
            C("name", "varchar(80)", nullable=False),
            C("category", "varchar(20)", nullable=False),
            C("country", "varchar(2)", nullable=False),
        ], merchants, [], (880, 20)),
        Table("transactions", "Signed ledger entries: positive amounts are money in.", [
            C("id", "integer", primary_key=True, identity=True),
            C("account_id", "integer", nullable=False, references="accounts.id"),
            C("posted_at", "timestamp", nullable=False),
            C("amount", "decimal(12,2)", nullable=False),
            C("kind", "varchar(12)", nullable=False, check=f"kind IN ({kinds})"),
            C("merchant_id", "integer", references="merchants.id"),
            C("counterparty_account_id", "integer", references="accounts.id"),
            C("description", "varchar(120)", nullable=False),
        ], transactions, [Index("idx_transactions_account_time", ("account_id", "posted_at"))], (560, 20)),
        Table("fx_rates", "US dollars per unit of currency, published on weekdays only.", [
            C("rate_date", "date", primary_key=True),
            C("currency", "varchar(3)", primary_key=True),
            C("usd_per_unit", "decimal(12,6)", nullable=False),
        ], rates, [], (880, 200)),
    ]
    return Dataset(
        id="bank",
        title="Tidewater bank",
        summary="A retail bank: accounts, a year of signed transactions, merchants and FX rates.",
        description=(
            "Tidewater Bank is fictional. Transactions run from 2025-07-01 to the snapshot date, "
            "**2026-07-01**. Amounts are signed: deposits and incoming transfers are positive, spending "
            "is negative. FX rates exist only on weekdays, which makes as-of joins necessary. A few "
            "accounts contain bursts of overseas card spending worth investigating."
        ),
        tables=tables,
    )
