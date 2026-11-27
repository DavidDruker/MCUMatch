"""Load and use limits: rule out when a lower bound exceeds a share of the budget.

By default a part is ruled out only when the best case exceeds the whole deadline, or the smallest
build exceeds the whole capacity. Engineers rarely plan to use all of either, so each limit can be
lowered: `--max-load 70` rules a part out when the best-case time is above 70 % of the deadline.

That is still a proven statement about a lower bound. It is not a claim that anything below the
limit works, and no verdict ever says so.

Limits are exact fractions, so "exactly at the limit" is decided without rounding.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

FULL = Fraction(1)


@dataclass(frozen=True)
class Limits:
    load: Fraction = FULL  # share of the deadline the best-case time may use
    flash: Fraction = FULL  # share of the flash capacity the smallest build may use
    ram: Fraction = FULL  # share of the RAM capacity the smallest build may use

    @property
    def any_set(self) -> bool:
        return (self.load, self.flash, self.ram) != (FULL, FULL, FULL)

    def as_json(self) -> dict[str, float]:
        return {"load": float(self.load), "flash_use": float(self.flash), "ram_use": float(self.ram)}


def parse_percent(text: str | float | int, what: str = "limit") -> Fraction:
    """'70', '70%' or '62.5' as an exact fraction. It must be above 0 and at most 100."""
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*%?\s*", str(text))
    value = Fraction(m[1]) / 100 if m else None
    if value is None or not 0 < value <= 1:
        raise ValueError(f"bad {what} {text!r}: use a percentage above 0 and at most 100, e.g. 70")
    return value


def format_percent(share: Fraction | float) -> str:
    """A limit the user chose, as typed: 70 %, 62.5 %."""
    return f"{float(share) * 100:.6g} %"


def format_duration_limit(load: Fraction, allowed: str) -> str:
    """'70 % load limit (70.000 us)': a load limit with the time it allows."""
    return f"{format_percent(load)} load limit ({allowed})"


def format_at_least(share: float) -> str:
    """A lower bound on a share, rounded DOWN so the printed figure never exceeds the bound:
    82.3 %, 2,715.5 %, 0.005 %."""
    pct = share * 100
    digits = 1 if pct >= 1 else 3
    scale = 10 ** digits
    return f"{math.floor(pct * scale) / scale:,.{digits}f} %"
