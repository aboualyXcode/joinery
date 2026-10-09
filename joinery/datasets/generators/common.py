"""Helpers shared by the dataset generators.

Generators must be deterministic: they only use a seeded ``random.Random``,
iterate over lists (never sets), and never read the clock.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import date, datetime, timedelta

FIRST_NAMES = [
    "Amara", "Bilal", "Chen", "Dalia", "Emeka", "Freya", "Gabriel", "Hana", "Ines", "Jonas",
    "Kofi", "Layla", "Mateo", "Nadia", "Oskar", "Priya", "Quentin", "Rosa", "Samir", "Tove",
    "Uma", "Viktor", "Wen", "Ximena", "Yusuf", "Zoe", "Aiko", "Bruno", "Clara", "Dmitri",
    "Elif", "Farah", "Goran", "Helga", "Ivan", "Jasmine", "Kenji", "Lucia", "Malik", "Noor",
    "Omar", "Paula", "Rafael", "Sofia", "Tariq", "Ula", "Valeria", "Wiktor", "Yara", "Zain",
    "Anika", "Ben", "Carmen", "Diego", "Esther", "Femi", "Greta", "Hugo", "Isla", "Jamal",
]
LAST_NAMES = [
    "Adeyemi", "Bauer", "Castillo", "Dubois", "Eriksen", "Fischer", "Garcia", "Haddad", "Ito", "Jansen",
    "Kowalski", "Larsen", "Mensah", "Nakamura", "Okafor", "Petrov", "Quinn", "Rossi", "Schmidt", "Tanaka",
    "Usman", "Varga", "Walsh", "Xu", "Yilmaz", "Zhang", "Abbas", "Brennan", "Costa", "Dahl",
    "Esposito", "Farouk", "Gomez", "Horvat", "Ibrahim", "Jovanovic", "Kim", "Lindqvist", "Moreau", "Novak",
    "O'Brien", "Park", "Reyes", "Sato", "Torres", "Ueda", "Vasquez", "Weber", "Young", "Zimmermann",
]
CITIES: dict[str, list[str]] = {
    "US": ["Portland", "Austin", "Chicago", "Denver", "Boston", "Seattle", "Atlanta"],
    "GB": ["Leeds", "Bristol", "Manchester", "London", "Glasgow"],
    "DE": ["Berlin", "Hamburg", "Leipzig", "Munich"],
    "NL": ["Rotterdam", "Utrecht", "Amsterdam"],
    "FR": ["Lyon", "Lille", "Paris", "Nantes"],
    "CA": ["Toronto", "Montreal", "Vancouver"],
    "AU": ["Melbourne", "Brisbane", "Perth"],
    "SE": ["Malmo", "Uppsala", "Stockholm"],
    "JP": ["Osaka", "Kyoto", "Tokyo"],
    "EG": ["Cairo", "Alexandria", "Giza"],
}
COUNTRY_WEIGHTS = [("US", 34), ("GB", 16), ("DE", 11), ("NL", 7), ("FR", 7), ("CA", 7), ("AU", 5),
                   ("SE", 5), ("JP", 4), ("EG", 4)]


def weighted(rng: random.Random, options: Sequence[tuple[object, float]]):
    values = [value for value, _ in options]
    weights = [weight for _, weight in options]
    return rng.choices(values, weights=weights, k=1)[0]


def ts(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def day(moment: date | datetime) -> str:
    return moment.strftime("%Y-%m-%d")


def money(value: float) -> float:
    return round(value + 0.0, 2)


def between(rng: random.Random, start: datetime, end: datetime) -> datetime:
    seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, max(0, seconds)))


def daytime(rng: random.Random, moment: datetime) -> datetime:
    """Move a timestamp to a plausible waking hour on the same day."""
    hour = weighted(rng, [(h, w) for h, w in zip(range(24), [1, 1, 1, 1, 1, 2, 4, 7, 9, 10, 10, 10,
                                                              11, 10, 9, 9, 9, 10, 11, 12, 11, 8, 5, 2])])
    return moment.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59))


def person(rng: random.Random) -> tuple[str, str]:
    return rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)


def email_for(first: str, last: str, number: int, domain: str = "example.com") -> str:
    local = f"{first}.{last}".lower().replace("'", "").replace(" ", "")
    return f"{local}{number}@{domain}"
