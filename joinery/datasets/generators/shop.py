"""Copperleaf Tea & Coffee: a fictional online shop.

An e-commerce OLTP schema with customers, a product catalogue, orders, line
items, payments, reviews, stock levels and the company's org chart. Coffee
prices rose 6% on 2025-03-01, so older line items carry the old price.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from ..model import Column as C
from ..model import Dataset, Index, Table
from .common import CITIES, COUNTRY_WEIGHTS, between, daytime, email_for, money, person, ts, weighted

SEED = 2604
START = datetime(2024, 1, 1)
SNAPSHOT = datetime(2026, 7, 1)
PRICE_RISE = datetime(2025, 3, 1)
COFFEE = (5, 6, 7)
SEASON = {11: 1.6, 12: 2.0, 1: 0.8, 2: 0.85}

CATEGORIES = [
    (1, "Coffee", None), (2, "Tea", None), (3, "Equipment", None), (4, "Gifts", None),
    (5, "Single origin", 1), (6, "Blends", 1), (7, "Decaf", 1),
    (8, "Green tea", 2), (9, "Black tea", 2), (10, "Herbal", 2),
    (11, "Brewers", 3), (12, "Grinders", 3), (13, "Accessories", 3),
]

# sku, name, category_id, price, cost, weight_grams, launched_on, is_active, popularity
PRODUCTS = [
    ("CF-ETH-250", "Ethiopia Yirgacheffe 250g", 5, 16.50, 6.40, 250, "2023-06-01", True, 9),
    ("CF-COL-250", "Colombia Huila 250g", 5, 14.00, 5.30, 250, "2023-06-01", True, 10),
    ("CF-KEN-250", "Kenya Nyeri AA 250g", 5, 18.00, 7.10, 250, "2023-06-01", True, 6),
    ("CF-GUA-250", "Guatemala Antigua 250g", 5, 15.00, 5.80, 250, "2023-06-01", True, 7),
    ("CF-BRA-1K", "Brazil Cerrado 1kg", 5, 38.00, 15.20, 1000, "2023-06-01", True, 8),
    ("CF-SUM-250", "Sumatra Mandheling 250g", 5, 15.50, 6.00, 250, "2023-06-01", True, 5),
    ("CF-CRI-250", "Costa Rica Tarrazu 250g", 5, 16.00, 6.20, 250, "2024-04-15", True, 6),
    ("CF-RWA-250", "Rwanda Huye 250g", 5, 17.50, 6.90, 250, "2026-07-15", False, 0),
    ("CF-ESP-1K", "House Espresso Blend 1kg", 6, 34.00, 13.00, 1000, "2023-06-01", True, 12),
    ("CF-MOR-250", "Morning Ritual Blend 250g", 6, 12.50, 4.60, 250, "2023-06-01", True, 11),
    ("CF-NOW-250", "Night Owl Dark Roast 250g", 6, 12.50, 4.70, 250, "2023-06-01", True, 7),
    ("CF-SIG-500", "Copperleaf Signature Blend 500g", 6, 24.00, 9.20, 500, "2023-06-01", True, 9),
    ("CF-DEC-250", "Swiss Water Decaf Colombia 250g", 7, 15.00, 6.10, 250, "2023-06-01", True, 4),
    ("CF-DES-250", "Decaf Espresso 250g", 7, 14.50, 5.90, 250, "2024-09-01", True, 3),
    ("TE-SEN-100", "Sencha Kyoto 100g", 8, 11.00, 3.90, 100, "2023-06-01", True, 6),
    ("TE-DRW-100", "Dragon Well 100g", 8, 13.50, 5.00, 100, "2023-06-01", True, 4),
    ("TE-GYO-050", "Gyokuro Premium 50g", 8, 21.00, 9.50, 50, "2023-06-01", True, 2),
    ("TE-JAS-100", "Jasmine Pearls 100g", 8, 14.00, 5.40, 100, "2023-06-01", True, 5),
    ("TE-MAT-030", "Ceremonial Matcha 30g", 8, 24.00, 10.80, 30, "2024-02-01", True, 8),
    ("TE-ASS-100", "Assam Breakfast 100g", 9, 8.50, 2.60, 100, "2023-06-01", True, 7),
    ("TE-DAR-050", "Darjeeling First Flush 50g", 9, 15.00, 6.30, 50, "2023-06-01", True, 3),
    ("TE-EGB-100", "Earl Grey Bergamot 100g", 9, 9.50, 3.00, 100, "2023-06-01", True, 8),
    ("TE-LAP-100", "Lapsang Souchong 100g", 9, 10.50, 3.70, 100, "2023-06-01", False, 0),
    ("TE-CEY-100", "Ceylon Highlands 100g", 9, 9.00, 2.90, 100, "2023-06-01", True, 4),
    ("TE-CHA-050", "Chamomile Blossom 50g", 10, 7.50, 2.20, 50, "2023-06-01", True, 5),
    ("TE-PEP-050", "Peppermint Leaf 50g", 10, 6.50, 1.90, 50, "2023-06-01", True, 5),
    ("TE-ROO-100", "Rooibos Vanilla 100g", 10, 8.00, 2.40, 100, "2023-06-01", True, 4),
    ("TE-HIB-100", "Hibiscus Berry 100g", 10, 8.50, 2.60, 100, "2024-05-01", True, 3),
    ("TE-LEM-050", "Lemongrass Ginger 50g", 10, 7.00, 2.10, 50, "2025-01-15", True, 3),
    ("EQ-POD-01", "Ceramic Pour-Over Dripper", 11, 26.00, 9.00, 420, "2023-06-01", True, 4),
    ("EQ-FRP-1L", "French Press 1L", 11, 32.00, 12.50, 780, "2023-06-01", True, 4),
    ("EQ-TRP-01", "Travel Press", 11, 29.00, 11.00, 350, "2023-06-01", True, 3),
    ("EQ-CBJ-15", "Cold Brew Jar 1.5L", 11, 27.00, 9.80, 900, "2024-05-01", True, 3),
    ("EQ-GTP-08", "Glass Teapot 800ml", 11, 34.00, 13.00, 700, "2023-06-01", True, 2),
    ("EQ-GNK-01", "Gooseneck Kettle", 11, 59.00, 24.00, 1100, "2023-06-01", True, 3),
    ("EQ-HBG-01", "Hand Burr Grinder", 12, 69.00, 28.00, 640, "2023-06-01", True, 3),
    ("EQ-EBG-01", "Electric Burr Grinder", 12, 149.00, 72.00, 2600, "2023-06-01", True, 2),
    ("AC-FIL-100", "Paper Filters (100)", 13, 5.50, 1.20, 120, "2023-06-01", True, 6),
    ("AC-SCL-01", "Digital Brew Scale", 13, 39.00, 15.00, 450, "2023-06-01", True, 3),
    ("AC-INF-01", "Tea Infuser Basket", 13, 9.00, 2.50, 60, "2023-06-01", True, 4),
    ("AC-FRO-01", "Milk Frother", 13, 22.00, 8.00, 250, "2023-06-01", True, 2),
    ("AC-MUG-35", "Stoneware Mug 350ml", 13, 16.00, 5.00, 380, "2023-06-01", True, 5),
    ("AC-CAN-50", "Airtight Canister 500g", 13, 19.00, 6.50, 300, "2023-06-01", True, 3),
    ("GF-CDB-01", "Coffee Discovery Box", 4, 42.00, 18.00, 900, "2023-06-01", True, 4),
    ("GF-TTF-01", "Tea Tasting Flight", 4, 36.00, 14.00, 400, "2023-06-01", True, 3),
    ("GF-GC-025", "Gift Card 25", 4, 25.00, 25.00, None, "2023-06-01", True, 2),
    ("GF-GC-050", "Gift Card 50", 4, 50.00, 50.00, None, "2023-06-01", True, 1),
    ("GF-BSK-01", "Barista Starter Kit", 4, 119.00, 52.00, 2400, "2025-10-01", True, 2),
]
LOW_RATED = {11, 32}  # Night Owl Dark Roast, Travel Press

EMPLOYEES = [
    (1, "Imani", "Okoro", "Chief Executive Officer", "Leadership", None, "2019-03-01", 185000),
    (2, "Lars", "Henriksen", "VP Operations", "Operations", 1, "2019-06-15", 142000),
    (3, "Mei", "Tanaka", "VP Marketing", "Marketing", 1, "2020-01-10", 138000),
    (4, "Rahul", "Mehta", "Head of Engineering", "Engineering", 1, "2020-04-01", 150000),
    (5, "Sophie", "Laurent", "Finance Director", "Finance", 1, "2020-09-01", 132000),
    (6, "Kwame", "Asante", "Roastery Manager", "Operations", 2, "2019-08-01", 78000),
    (7, "Elena", "Petrova", "Warehouse Manager", "Operations", 2, "2021-02-15", 72000),
    (8, "Tomas", "Novak", "Customer Support Lead", "Operations", 2, "2021-05-03", 64000),
    (9, "Hiba", "Mansour", "Growth Marketing Lead", "Marketing", 3, "2021-03-22", 88000),
    (10, "Jack", "Murphy", "Brand Designer", "Marketing", 3, "2022-07-11", 69000),
    (11, "Ana", "Souza", "Engineering Manager", "Engineering", 4, "2021-01-18", 118000),
    (12, "Felix", "Wagner", "Data Engineer", "Engineering", 4, "2022-03-07", 98000),
    (13, "Leila", "Haddad", "Senior Accountant", "Finance", 5, "2022-02-01", 61000),
    (14, "Noah", "Becker", "Head Roaster", "Operations", 6, "2020-02-10", 58000),
    (15, "Priya", "Raman", "Roaster", "Operations", 14, "2023-04-17", 42000),
    (16, "Diego", "Morales", "Roaster", "Operations", 14, "2024-01-08", 40000),
    (17, "Grace", "Liu", "Warehouse Associate", "Operations", 7, "2022-10-03", 36000),
    (18, "Oluwaseun", "Bello", "Warehouse Associate", "Operations", 7, "2023-06-12", 35500),
    (19, "Marta", "Kowalczyk", "Warehouse Associate", "Operations", 7, "2024-09-02", 34000),
    (20, "Sami", "Virtanen", "Support Specialist", "Operations", 8, "2022-01-24", 41000),
    (21, "Chloe", "Martin", "Support Specialist", "Operations", 8, "2023-03-13", 40000),
    (22, "Yusuf", "Demir", "Support Specialist", "Operations", 8, "2025-02-03", 39000),
    (23, "Isabel", "Ferreira", "Content Marketer", "Marketing", 9, "2023-01-09", 57000),
    (24, "Arjun", "Nair", "Performance Marketer", "Marketing", 9, "2024-06-03", 60000),
    (25, "Hannah", "Schulz", "Backend Engineer", "Engineering", 11, "2022-05-16", 96000),
    (26, "Kenji", "Watanabe", "Frontend Engineer", "Engineering", 11, "2023-02-27", 92000),
    (27, "Fatima", "Zahra", "Backend Engineer", "Engineering", 11, "2024-08-19", 89000),
    (28, "Liam", "Connor", "Analytics Engineer", "Engineering", 12, "2025-04-14", 84000),
    (29, "Nina", "Kovac", "Payroll Specialist", "Finance", 13, "2024-03-04", 52000),
    (30, "Omar", "Saleh", "Junior Accountant", "Finance", 13, "2026-01-12", 46000),
]

TITLES = {
    5: ["Absolutely lovely", "New favourite", "Perfect every morning", "Worth every penny"],
    4: ["Really good", "Solid choice", "Would buy again"],
    3: ["Decent", "It's fine", "Not bad, not great"],
    2: ["Disappointing", "Expected more"],
    1: ["Would not recommend", "Arrived damaged", "Not for me"],
}
BODIES = {
    5: ["Fresh, aromatic and consistent. I order this every month.", "Exactly as described and arrived quickly."],
    4: ["Very good, though a little pricey.", "Lovely flavour, packaging could be better."],
    3: ["Fine for everyday use.", "Okay, but I prefer the blends."],
    2: ["Flavour was flat compared to the last bag.", "Took a long time to arrive."],
    1: ["The bag was split when it arrived.", "Too bitter for me, will not reorder."],
}


def _price_at(product_id: int, when: datetime) -> float:
    _sku, _name, category, price, *_rest = PRODUCTS[product_id - 1]
    if category in COFFEE and when < PRICE_RISE:
        return round(price / 1.06 * 2) / 2
    return price


def _seasonal(rng: random.Random, lo: datetime, hi: datetime) -> datetime:
    moment = between(rng, lo, hi)
    for _ in range(20):
        if rng.random() < SEASON.get(moment.month, 1.0) / 2.0:
            break
        moment = between(rng, lo, hi)
    moment = daytime(rng, moment)
    return moment if moment > lo else lo + timedelta(minutes=rng.randint(5, 180))


def build() -> Dataset:
    rng = random.Random(SEED)

    # Customers, numbered in sign-up order so referrers always signed up first.
    signups = sorted(daytime(rng, between(rng, datetime(2023, 6, 1), datetime(2026, 6, 20))) for _ in range(450))
    customers = []
    for cid, signed in enumerate(signups, start=1):
        first, last = person(rng)
        country = weighted(rng, COUNTRY_WEIGHTS)
        city = rng.choice(CITIES[country]) if rng.random() > 0.04 else None
        referred_by = rng.randint(1, cid - 1) if cid > 20 and rng.random() < 0.14 else None
        customers.append((cid, email_for(first, last, cid), first, last, city, country, ts(signed),
                          rng.random() < 0.55, referred_by))

    # Orders: timestamps first, then ids in chronological order.
    pending = []
    for cid, _email, *_rest in customers:
        signed = datetime.fromisoformat(customers[cid - 1][6])
        lo = max(signed, START)
        if lo >= SNAPSHOT - timedelta(days=1):
            continue
        n = weighted(rng, [(0, 7), (1, 24), (2, 17), (3, 13), (4, 10), (5, 8), (6, 6), (8, 6), (12, 6), (18, 3)])
        times = sorted(_seasonal(rng, lo, SNAPSHOT - timedelta(hours=1)) for _ in range(n))
        for position, moment in enumerate(times):
            pending.append((moment, cid, position == 0))
    pending.sort(key=lambda item: (item[0], item[1]))

    countries = [code for code, _ in COUNTRY_WEIGHTS]
    orders, items, payments, reviews = [], [], [], []
    reviewed: set[tuple[int, int]] = set()
    payment_id = 0
    for oid, (moment, cid, first_order) in enumerate(pending, start=1):
        age = (SNAPSHOT - moment).days
        if age < 2:
            status = weighted(rng, [("pending", 40), ("paid", 60)])
        elif age < 6:
            status = weighted(rng, [("paid", 30), ("shipped", 70)])
        elif age < 12:
            status = weighted(rng, [("shipped", 40), ("delivered", 60)])
        else:
            status = weighted(rng, [("delivered", 84), ("cancelled", 9), ("refunded", 7)])
        channel = weighted(rng, [("web", 60), ("mobile", 30), ("marketplace", 10)])
        country = customers[cid - 1][5] if rng.random() < 0.96 else rng.choice(countries)
        code, pct = None, 0.0
        if rng.random() < 0.12:
            if first_order and rng.random() < 0.6:
                code, pct = "WELCOME10", 0.10
            elif moment.month in (11, 12):
                code, pct = "HOLIDAY20", 0.20
            elif moment.month in (3, 4):
                code, pct = "SPRING15", 0.15
            else:
                code, pct = "LOYAL10", 0.10
        shipped = delivered = None
        if status in ("shipped", "delivered", "refunded"):
            shipped = moment + timedelta(days=rng.randint(1, 3), hours=rng.randint(0, 8))
            if shipped >= SNAPSHOT:
                shipped, status = None, "paid"
        if shipped and status in ("delivered", "refunded"):
            delivered = shipped + timedelta(days=rng.randint(2, 6), hours=rng.randint(0, 10))
            if delivered >= SNAPSHOT:
                delivered, status = None, "shipped"

        pool = [(pid, p[8]) for pid, p in enumerate(PRODUCTS, start=1)
                if p[7] and p[8] > 0 and datetime.fromisoformat(p[6]) <= moment]
        chosen: list[int] = []
        for _ in range(weighted(rng, [(1, 48), (2, 30), (3, 15), (4, 7)])):
            pid = weighted(rng, pool)
            if pid not in chosen:
                chosen.append(pid)
        total = 0.0
        for line_no, pid in enumerate(chosen, start=1):
            qty = weighted(rng, [(1, 70), (2, 22), (3, 6), (4, 1), (6, 1)])
            price = _price_at(pid, moment)
            discount = money(price * qty * pct)
            total += price * qty - discount
            items.append((oid, line_no, pid, qty, price, discount))
        total = money(total)
        orders.append((oid, cid, ts(moment), status, channel, country, code,
                       ts(shipped) if shipped else None, ts(delivered) if delivered else None))

        if status != "pending":
            method = weighted(rng, [("card", 65), ("paypal", 25), ("gift_card", 5), ("bank_transfer", 5)])
            if method == "card" and rng.random() < 0.04:
                payment_id += 1
                payments.append((payment_id, oid, ts(moment + timedelta(minutes=1)), "card", total, "failed"))
            paid_at = moment + timedelta(minutes=rng.randint(2, 40))
            payment_id += 1
            payments.append((payment_id, oid, ts(paid_at), method, total, "captured"))
            refund_at = None
            if status == "cancelled":
                refund_at = paid_at + timedelta(hours=rng.randint(2, 30))
            elif status == "refunded" and delivered:
                refund_at = delivered + timedelta(days=rng.randint(2, 14))
            if refund_at and refund_at < SNAPSHOT:
                payment_id += 1
                payments.append((payment_id, oid, ts(refund_at), method, -total, "refunded"))
            elif status == "refunded":
                status = "delivered"
                orders[-1] = orders[-1][:3] + (status,) + orders[-1][4:]

        if delivered:
            for pid in chosen:
                if (cid, pid) in reviewed or rng.random() > 0.22:
                    continue
                created = delivered + timedelta(days=rng.randint(1, 20), hours=rng.randint(0, 12))
                if created >= SNAPSHOT:
                    continue
                reviewed.add((cid, pid))
                if status == "refunded":
                    weights = [(1, 40), (2, 30), (3, 20), (4, 7), (5, 3)]
                elif pid in LOW_RATED:
                    weights = [(1, 12), (2, 18), (3, 25), (4, 25), (5, 20)]
                else:
                    weights = [(1, 5), (2, 7), (3, 12), (4, 30), (5, 46)]
                rating = weighted(rng, weights)
                body = rng.choice(BODIES[rating]) if rng.random() < 0.65 else None
                reviews.append((len(reviews) + 1, pid, cid, rating, rng.choice(TITLES[rating]), body, ts(created)))

    products = [
        (pid, sku, name, cat, price, cost, weight, launched, active)
        for pid, (sku, name, cat, price, cost, weight, launched, active, _pop) in enumerate(PRODUCTS, start=1)
    ]
    inventory = []
    for pid, (sku, _n, cat, *_r) in enumerate(PRODUCTS, start=1):
        if sku.startswith("GF-GC") or sku == "CF-RWA-250":
            continue
        reorder = rng.choice([20, 30, 40, 60])
        on_hand = rng.randint(0, reorder - 1) if rng.random() < 0.18 else rng.randint(reorder, 400)
        warehouse = "Rotterdam" if cat in COFFEE else "Leeds"
        updated = SNAPSHOT - timedelta(hours=rng.randint(1, 240))
        inventory.append((pid, warehouse, on_hand, reorder, ts(updated)))

    employees = [
        (eid, first, last, title, dept, manager, hired, float(salary),
         f"{first}.{last}".lower() + "@copperleaf.example")
        for eid, first, last, title, dept, manager, hired, salary in EMPLOYEES
    ]

    statuses = "'pending', 'paid', 'shipped', 'delivered', 'cancelled', 'refunded'"
    tables = [
        Table("customers", "People with a Copperleaf account.", [
            C("id", "integer", primary_key=True, identity=True),
            C("email", "varchar(120)", nullable=False, unique=True),
            C("first_name", "varchar(60)", nullable=False),
            C("last_name", "varchar(60)", nullable=False),
            C("city", "varchar(60)", doc="Missing for a few customers."),
            C("country", "varchar(2)", nullable=False, doc="ISO 3166-1 alpha-2 code."),
            C("signed_up_at", "timestamp", nullable=False),
            C("marketing_opt_in", "boolean", nullable=False, default="FALSE"),
            C("referred_by", "integer", references="customers.id", doc="The customer who referred them."),
        ], customers, [Index("idx_customers_country", ("country",))], (20, 20)),
        Table("categories", "Product categories; subcategories point to their parent.", [
            C("id", "integer", primary_key=True, identity=True),
            C("name", "varchar(60)", nullable=False, unique=True),
            C("parent_id", "integer", references="categories.id"),
        ], CATEGORIES, [], (1100, 20)),
        Table("products", "The catalogue. unit_price is today's price.", [
            C("id", "integer", primary_key=True, identity=True),
            C("sku", "varchar(20)", nullable=False, unique=True),
            C("name", "varchar(80)", nullable=False),
            C("category_id", "integer", nullable=False, references="categories.id"),
            C("unit_price", "decimal(10,2)", nullable=False, check="unit_price >= 0"),
            C("cost", "decimal(10,2)", nullable=False),
            C("weight_grams", "integer", doc="NULL for digital gift cards."),
            C("launched_on", "date", nullable=False),
            C("is_active", "boolean", nullable=False, default="TRUE"),
        ], products, [], (830, 20)),
        Table("orders", "One row per checkout. customer_id is deliberately left unindexed.", [
            C("id", "integer", primary_key=True, identity=True),
            C("customer_id", "integer", nullable=False, references="customers.id"),
            C("ordered_at", "timestamp", nullable=False),
            C("status", "varchar(12)", nullable=False, default="'pending'", check=f"status IN ({statuses})"),
            C("channel", "varchar(12)", nullable=False, check="channel IN ('web', 'mobile', 'marketplace')"),
            C("shipping_country", "varchar(2)", nullable=False),
            C("discount_code", "varchar(20)"),
            C("shipped_at", "timestamp"),
            C("delivered_at", "timestamp"),
        ], orders, [Index("idx_orders_ordered_at", ("ordered_at",))], (290, 20)),
        Table("order_items", "Line items. unit_price is the price at the time of the order.", [
            C("order_id", "integer", primary_key=True, references="orders.id"),
            C("line_no", "integer", primary_key=True),
            C("product_id", "integer", nullable=False, references="products.id"),
            C("quantity", "integer", nullable=False, check="quantity > 0"),
            C("unit_price", "decimal(10,2)", nullable=False),
            C("discount", "decimal(10,2)", nullable=False, default="0"),
        ], items, [Index("idx_order_items_product", ("product_id",))], (560, 20)),
        Table("payments", "Payment attempts, captures and refunds (refunds are negative).", [
            C("id", "integer", primary_key=True, identity=True),
            C("order_id", "integer", nullable=False, references="orders.id"),
            C("paid_at", "timestamp", nullable=False),
            C("method", "varchar(16)", nullable=False),
            C("amount", "decimal(10,2)", nullable=False),
            C("status", "varchar(10)", nullable=False, check="status IN ('captured', 'failed', 'refunded')"),
        ], payments, [Index("idx_payments_order", ("order_id",))], (290, 290)),
        Table("reviews", "Product reviews written after delivery.", [
            C("id", "integer", primary_key=True, identity=True),
            C("product_id", "integer", nullable=False, references="products.id"),
            C("customer_id", "integer", nullable=False, references="customers.id"),
            C("rating", "integer", nullable=False, check="rating BETWEEN 1 AND 5"),
            C("title", "varchar(80)", nullable=False),
            C("body", "text"),
            C("created_at", "timestamp", nullable=False),
        ], reviews, [Index("idx_reviews_product", ("product_id",))], (560, 210)),
        Table("inventory", "Stock on hand per product. Gift cards are not stocked.", [
            C("product_id", "integer", primary_key=True, references="products.id"),
            C("warehouse", "varchar(20)", nullable=False),
            C("on_hand", "integer", nullable=False, check="on_hand >= 0"),
            C("reorder_level", "integer", nullable=False),
            C("updated_at", "timestamp", nullable=False),
        ], inventory, [], (830, 260)),
        Table("employees", "Copperleaf staff. manager_id forms the org chart.", [
            C("id", "integer", primary_key=True, identity=True),
            C("first_name", "varchar(60)", nullable=False),
            C("last_name", "varchar(60)", nullable=False),
            C("title", "varchar(60)", nullable=False),
            C("department", "varchar(30)", nullable=False),
            C("manager_id", "integer", references="employees.id"),
            C("hired_on", "date", nullable=False),
            C("salary", "decimal(10,2)", nullable=False, check="salary > 0"),
            C("email", "varchar(120)", nullable=False, unique=True),
        ], employees, [], (20, 290)),
    ]
    return Dataset(
        id="shop",
        title="Copperleaf shop",
        summary="An online tea and coffee shop: customers, orders, payments, reviews and staff.",
        description=(
            "Copperleaf Tea & Coffee is a fictional online shop. The data runs from January 2024 to the "
            "snapshot date, **2026-07-01**. Coffee prices rose 6% on 2025-03-01, so older line items "
            "carry the old price. Refunds appear as negative payments. `orders.customer_id` has no index "
            "on purpose, so you can measure what adding one changes."
        ),
        tables=tables,
    )

