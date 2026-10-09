"""A deliberately tiny dataset for seeing joins and set operations row by row.

The Foxes have no players, and two players have no team, so every join type
produces a visibly different result.
"""

from __future__ import annotations

from ..model import Column as C
from ..model import Dataset, Table


def build() -> Dataset:
    teams = [(1, "Comets", "Leeds"), (2, "Herons", "Lagos"), (3, "Owls", "Lima"), (4, "Foxes", "Lyon")]
    players = [
        (1, "Ada", 1, "captain"), (2, "Bo", 1, "keeper"), (3, "Cy", 2, "striker"), (4, "Di", 2, "defender"),
        (5, "Eve", 3, "midfield"), (6, "Fin", None, "striker"), (7, "Gus", None, "keeper"),
    ]
    tables = [
        Table("teams", "Four teams. The Foxes have no players yet.", [
            C("id", "integer", primary_key=True, identity=True),
            C("name", "varchar(20)", nullable=False, unique=True),
            C("city", "varchar(20)", nullable=False),
        ], teams, [], (20, 20)),
        Table("players", "Seven players. Fin and Gus have not joined a team.", [
            C("id", "integer", primary_key=True, identity=True),
            C("name", "varchar(20)", nullable=False),
            C("team_id", "integer", references="teams.id"),
            C("role", "varchar(12)", nullable=False),
        ], players, [], (300, 20)),
    ]
    return Dataset(
        id="joinlab",
        title="Join lab",
        summary="Two tiny tables built to make every join type look different.",
        description=(
            "Four teams and seven players. The Foxes have no players and Fin and Gus have no team, "
            "so inner, outer, semi and anti joins all return visibly different rows."
        ),
        tables=tables,
    )
