"""Stable GitHub repository identities across owner and name changes."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from limen.conduct.models import ProtocolModel


_COORDINATE_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class RepositoryIdentityV1(ProtocolModel):
    """One immutable GitHub repository ID plus its live and historical coordinates."""

    schema_version: Literal["limen.repository_identity.v1"] = "limen.repository_identity.v1"
    repository_id: int = Field(gt=0)
    canonical_coordinate: str
    historical_aliases: tuple[str, ...]

    @field_validator("canonical_coordinate")
    @classmethod
    def validate_canonical_coordinate(cls, value: str) -> str:
        if value != value.strip() or not _COORDINATE_RE.fullmatch(value):
            raise ValueError("canonical coordinate must be exact OWNER/REPO")
        return value

    @field_validator("historical_aliases")
    @classmethod
    def validate_historical_aliases(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(value != value.strip() or not _COORDINATE_RE.fullmatch(value) for value in values):
            raise ValueError("historical aliases must be exact OWNER/REPO coordinates")
        return values

    @model_validator(mode="after")
    def coordinates_are_unique(self) -> "RepositoryIdentityV1":
        coordinates = (self.canonical_coordinate, *self.historical_aliases)
        if len(coordinates) != len({coordinate.casefold() for coordinate in coordinates}):
            raise ValueError("canonical coordinate and historical aliases must be unique")
        return self

    @property
    def coordinates(self) -> frozenset[str]:
        return frozenset((self.canonical_coordinate, *self.historical_aliases))

    def accepts(self, coordinate: str) -> bool:
        candidate = coordinate.strip().casefold()
        return candidate in {value.casefold() for value in self.coordinates}

    def canonicalize(self, coordinate: str) -> str:
        """Resolve a current or historical coordinate without changing stable identity."""

        if not self.accepts(coordinate):
            raise ValueError("coordinate does not belong to this repository identity")
        return self.canonical_coordinate

    def stable_key(self, suffix: str) -> str:
        suffix = suffix.strip()
        if not suffix or "\x00" in suffix:
            raise ValueError("repository identity key suffix must be nonblank")
        return f"github-repository:{self.repository_id}/{suffix}"


LIMEN_REPOSITORY_IDENTITY = RepositoryIdentityV1(
    repository_id=1_255_213_941,
    canonical_coordinate="4444J99/limen",
    historical_aliases=("organvm/limen",),
)

# This is a transfer destination of last resort, not an identity alias.  It must not be accepted
# as canonical until GitHub has refused the preferred destination before mutation and the same
# numeric repository has actually landed there.  A fallback transfer therefore leaves every
# workflow frozen until a follow-up identity/defaults change makes this coordinate canonical.
LIMEN_TRANSFER_FALLBACK_COORDINATE = "4444J99/limen-control"
