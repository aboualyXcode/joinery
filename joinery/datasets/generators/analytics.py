"""Product analytics for the Copperleaf website, plus roastery sensor readings.

Users browse in sessions; some add to cart, start checkout and purchase.
Event properties are JSON. An A/B test ("checkout_v2") slightly improves
checkout conversion. Sensors report every 15 minutes, with random gaps and
one six-hour outage.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta

from ..model import Column as C
from ..model import Dataset, Index, Table
from .common import COUNTRY_WEIGHTS, between, day, daytime, ts, weighted

SEED = 4242
START = datetime(2026, 1, 1)
SNAPSHOT = datetime(2026, 7, 1)

CAMPAIGNS = [
    (1, "new-year-reset", "social", "2026-01-02", "2026-01-31", 6000.0),
    (2, "valentine-gifts", "email", "2026-02-01", "2026-02-14", 2500.0),
    (3, "spring-sale", "search", "2026-03-15", "2026-04-15", 9000.0),
    (4, "matcha-launch", "social", "2026-04-20", "2026-05-20", 7000.0),
    (5, "partner-cafes", "partner", "2026-05-01", "2026-06-30", 4000.0),
    (6, "summer-cold-brew", "search", "2026-06-01", "2026-06-30", 8000.0),
]
PAGES = ["/", "/shop/coffee", "/shop/tea", "/shop/equipment", "/blog/brew-guide", "/product/CF-ETH-250",
         "/product/CF-ESP-1K", "/product/TE-MAT-030", "/product/TE-EGB-100", "/product/EQ-HBG-01"]
QUERIES = ["matcha", "decaf", "espresso", "grinder", "earl grey", "cold brew", "gift", "kenya", "chai"]
CART_ITEMS = [("CF-ETH-250", 16.5), ("CF-ESP-1K", 34.0), ("TE-MAT-030", 24.0), ("TE-EGB-100", 9.5),
              ("CF-MOR-250", 12.5), ("EQ-HBG-01", 69.0), ("AC-FIL-100", 5.5), ("GF-CDB-01", 42.0)]
SENSORS = [("roastery-1", 24.0, 1.0), ("warehouse-a", 18.0, 2.0), ("warehouse-b", 19.0, 2.5)]


def build() -> Dataset:
    rng = random.Random(SEED)
    signups = sorted(daytime(rng, between(rng, START, datetime(2026, 6, 20))) for _ in range(800))
    users, assignments, raw_events = [], [], []
    for uid, signed in enumerate(signups, start=1):
        platform = weighted(rng, [("web", 50), ("ios", 30), ("android", 20)])
        tier = weighted(rng, [("free", 80), ("pro", 17), ("team", 3)])
        referrer = weighted(rng, [("organic", 45), ("ads", 25), ("social", 18), ("partner", 12)])
        users.append((uid, ts(signed), weighted(rng, COUNTRY_WEIGHTS), platform, tier, referrer))
        variant = None
        if signed >= datetime(2026, 3, 1) and rng.random() < 0.6:
            variant = "treatment" if rng.random() < 0.5 else "control"
            assignments.append((uid, "checkout_v2", variant, ts(signed)))
        device = "desktop" if platform == "web" and rng.random() < 0.7 else "mobile"
        raw_events.append((signed, uid, f"s{uid}-0", "signup", "/signup", {"device": device}))

        sessions = weighted(rng, [(1, 30), (2, 20), (3, 14), (4, 10), (6, 10), (9, 8), (14, 8)])
        starts = sorted(daytime(rng, between(rng, signed + timedelta(minutes=5), SNAPSHOT - timedelta(hours=2)))
                        for _ in range(sessions))
        for n, moment in enumerate(starts, start=1):
            sid = f"s{uid}-{n}"
            props: dict = {"device": device}
            active = [c for c in CAMPAIGNS if c[3] <= day(moment) <= c[4]]
            if active and rng.random() < 0.25:
                props["utm_campaign"] = rng.choice(active)[1]
            raw_events.append((moment, uid, sid, "page_view", rng.choice(PAGES[:5]), props))
            for _ in range(rng.randint(0, 5)):
                moment += timedelta(seconds=rng.randint(15, 240))
                if rng.random() < 0.25:
                    query = rng.choice(QUERIES)
                    raw_events.append((moment, uid, sid, "search", "/search", {"query": query, "results": rng.randint(0, 14)}))
                else:
                    raw_events.append((moment, uid, sid, "page_view", rng.choice(PAGES), {"device": device}))
            if rng.random() > 0.33:
                continue
            cart = rng.sample(CART_ITEMS, rng.randint(1, 3))
            value = 0.0
            for sku, price in cart:
                moment += timedelta(seconds=rng.randint(20, 180))
                qty = 1 if rng.random() < 0.8 else 2
                value += price * qty
                raw_events.append((moment, uid, sid, "add_to_cart", f"/product/{sku}", {"sku": sku, "price": price, "quantity": qty}))
            if rng.random() > 0.58:
                continue
            moment += timedelta(seconds=rng.randint(30, 300))
            raw_events.append((moment, uid, sid, "checkout_start", "/checkout", {"cart_value": round(value, 2), "items": len(cart)}))
            rate = {"treatment": 0.71, "control": 0.62}.get(variant or "", 0.64)
            if rng.random() < rate:
                moment += timedelta(seconds=rng.randint(40, 400))
                payment = weighted(rng, [("card", 70), ("paypal", 30)])
                raw_events.append((moment, uid, sid, "purchase", "/checkout/complete",
                                   {"order_value": round(value, 2), "items": len(cart), "payment": payment}))

    raw_events = [e for e in raw_events if e[0] < SNAPSHOT]
    raw_events.sort(key=lambda e: (e[0], e[1], e[3]))
    events = [(eid, uid, sid, ts(moment), name, page, json.dumps(props, separators=(",", ":")))
              for eid, (moment, uid, sid, name, page, props) in enumerate(raw_events, start=1)]

    readings = []
    outage = (datetime(2026, 6, 9, 2), datetime(2026, 6, 9, 8))
    for sensor, base, swing in SENSORS:
        moment = datetime(2026, 6, 1)
        while moment < datetime(2026, 6, 15):
            missing = rng.random() < 0.02 or (sensor == "warehouse-b" and outage[0] <= moment < outage[1])
            if not missing:
                hour = moment.hour + moment.minute / 60
                temp = base + swing * math.sin((hour - 9) / 24 * 2 * math.pi) + rng.gauss(0, 0.3)
                if sensor == "roastery-1" and moment.weekday() < 5 and 8 <= moment.hour < 11:
                    temp += 9 + rng.uniform(0, 4)
                humidity = 50 + 8 * math.cos(hour / 24 * 2 * math.pi) + rng.gauss(0, 1.5)
                readings.append((sensor, ts(moment), round(temp, 2), round(humidity, 1)))
            moment += timedelta(minutes=15)

    tables = [
        Table("users", "People who signed up on the website or apps.", [
            C("id", "integer", primary_key=True, identity=True),
            C("signed_up_at", "timestamp", nullable=False),
            C("country", "varchar(2)", nullable=False),
            C("platform", "varchar(10)", nullable=False, check="platform IN ('web', 'ios', 'android')"),
            C("tier", "varchar(10)", nullable=False, check="tier IN ('free', 'pro', 'team')"),
            C("referrer", "varchar(10)", nullable=False),
        ], users, [], (20, 20)),
        Table("events", "Clickstream events. properties holds JSON.", [
            C("id", "integer", primary_key=True, identity=True),
            C("user_id", "integer", nullable=False, references="users.id"),
            C("session_id", "varchar(20)", nullable=False),
            C("occurred_at", "timestamp", nullable=False),
            C("name", "varchar(20)", nullable=False),
            C("page", "varchar(60)", nullable=False),
            C("properties", "json", nullable=False),
        ], events, [Index("idx_events_occurred_at", ("occurred_at",))], (290, 20)),
        Table("campaigns", "Marketing campaigns, matched to events through properties.utm_campaign.", [
            C("id", "integer", primary_key=True, identity=True),
            C("name", "varchar(40)", nullable=False, unique=True),
            C("channel", "varchar(10)", nullable=False),
            C("started_on", "date", nullable=False),
            C("ended_on", "date", nullable=False),
            C("budget", "decimal(10,2)", nullable=False),
        ], CAMPAIGNS, [], (560, 20)),
        Table("experiments", "A/B test assignments.", [
            C("user_id", "integer", primary_key=True, references="users.id"),
            C("experiment", "varchar(30)", primary_key=True),
            C("variant", "varchar(10)", nullable=False, check="variant IN ('control', 'treatment')"),
            C("assigned_at", "timestamp", nullable=False),
        ], assignments, [], (20, 230)),
        Table("sensor_readings", "Temperature and humidity every 15 minutes, with gaps.", [
            C("sensor_id", "varchar(20)", primary_key=True),
            C("read_at", "timestamp", primary_key=True),
            C("temperature_c", "decimal(5,2)", nullable=False),
            C("humidity_pct", "decimal(5,1)", nullable=False),
        ], readings, [], (560, 230)),
    ]
    return Dataset(
        id="analytics",
        title="Copperleaf analytics",
        summary="Clickstream events with JSON properties, campaigns, an A/B test and sensor time series.",
        description=(
            "Website and app activity for Copperleaf from 2026-01-01 to **2026-07-01**. Each session "
            "is a sequence of events; some end in a purchase. `events.properties` is JSON. Users who "
            "signed up after March were split into the `checkout_v2` experiment. `sensor_readings` "
            "covers two weeks in June every 15 minutes, with random gaps and a six-hour outage."
        ),
        tables=tables,
    )
