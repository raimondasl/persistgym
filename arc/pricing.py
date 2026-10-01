"""Gemini prices for the ARC runs and the cost of a run's recorded usage.

One table, `PRICES`, in USD per million tokens. Source: the Gemini API pricing page,
https://ai.google.dev/gemini-api/docs/pricing, checked 2026-09-30 (PLAN.md §12,
docs/background.md §6; the same numbers are in analysis/data/prices.csv). Gemini 3.8 Flash
costs $0.75 input, $0.075 cached input and $3.75 output (thinking included) "through
December 31, 2026"; the prices double on 2027-01-01, so `price_for` refuses a date after
`valid_through`.

Two estimates per run, from the harness's own usage records (step_NNN.json and
compaction_NNN.json, whose `prompt_tokens` include cached tokens and whose
`completion_tokens` include thought tokens):

* `cost_usd_list`: ARC's no-cache list accounting, every input token at the input price.
  This is what ARC publishes and what the harness's cost guard (patch 0010) counts.
* `cost_usd_billed_est`: the standard tier as billed, cached input at the cached price
  (D21, D23). It is the primary cost basis; the invoice is the truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

PRICE_SOURCE_URL = "https://ai.google.dev/gemini-api/docs/pricing"
PRICE_SOURCE_DATE = "2026-09-30"
TIER = "standard"


@dataclass(frozen=True)
class Price:
    input: float
    cached: float
    output: float
    valid_through: date


PRICES: dict[tuple[str, str], Price] = {
    ("gemini-3.8-flash", "standard"): Price(0.75, 0.075, 3.75, date(2026, 12, 31)),
}


class PriceError(ValueError):
    pass


def price_for(model: str, tier: str = TIER, *, on: date | None = None) -> Price:
    """The price of `model` on `tier`, refusing a model or tier the table does not have and
    a date after the price's `valid_through`."""
    p = PRICES.get((model, tier))
    if p is None:
        raise PriceError(f"no price for model {model!r} on the {tier!r} tier; add it to "
                         "arc/pricing.py PRICES with its source")
    if on is not None and on > p.valid_through:
        raise PriceError(f"the {model} {tier} price is valid through {p.valid_through}; "
                         f"{on} is later (Gemini 3.8 Flash prices double on 2027-01-01)")
    return p


@dataclass(frozen=True)
class Usage:
    """Token counts as the harness records them (`StepUsage`)."""
    prompt_tokens: int = 0       # input, cached included
    cached_tokens: int = 0       # cached part of the input
    completion_tokens: int = 0   # output, thought tokens included
    reasoning_tokens: int = 0    # thought tokens (part of completion_tokens)

    @classmethod
    def from_record(cls, usage: dict | None) -> Usage:
        u = usage or {}
        values = {k: u.get(k) or 0 for k in ("prompt_tokens", "cached_tokens",
                                             "completion_tokens", "reasoning_tokens")}
        for k, v in values.items():
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise PriceError(f"usage {k}={v!r} is not a non-negative integer")
        if values["cached_tokens"] > values["prompt_tokens"]:
            raise PriceError(f"usage has more cached tokens ({values['cached_tokens']}) than "
                             f"input tokens ({values['prompt_tokens']})")
        return cls(**values)

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.prompt_tokens + other.prompt_tokens,
                     self.cached_tokens + other.cached_tokens,
                     self.completion_tokens + other.completion_tokens,
                     self.reasoning_tokens + other.reasoning_tokens)

    def minus(self, other: Usage) -> Usage:
        """`self - other` per field, floored at 0 (the part of a run total that no record
        holds, such as a failed summary request's usage)."""
        return Usage(*(max(a - b, 0) for a, b in (
            (self.prompt_tokens, other.prompt_tokens),
            (self.cached_tokens, other.cached_tokens),
            (self.completion_tokens, other.completion_tokens),
            (self.reasoning_tokens, other.reasoning_tokens))))


def cost_usd(usage: Usage, price: Price) -> tuple[float, float]:
    """(list, billed estimate) in USD for `usage` at `price`."""
    listed = (usage.prompt_tokens * price.input + usage.completion_tokens * price.output) / 1e6
    uncached = max(usage.prompt_tokens - usage.cached_tokens, 0)
    billed = (uncached * price.input + usage.cached_tokens * price.cached
              + usage.completion_tokens * price.output) / 1e6
    return listed, billed
