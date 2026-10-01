"""OpenAI prices and a per-run usage ledger that produces the results/costs.csv row.

Prices (USD per million tokens), checked 2026-09-30 (PLAN.md §12, docs/background.md §6):
* gpt-6-luna: $0.10 input / $0.01 cached / $0.50 output
  (https://developers.openai.com/api/docs/pricing)
* gpt-6.1-sol: $2.00 / $0.10 / $10.00 (same source)
* Flex: 50% off (https://developers.openai.com/api/docs/guides/flex-processing)
* Cache writes: "1.25x the standard, uncached input-token rate" on GPT-5.6 and later
  (https://developers.openai.com/api/docs/guides/prompt-caching; PLAN §16.1)

`cost_usd_list` is the standard-tier price of the usage; `cost_usd_billed_est` applies the
Flex discount when the response's echoed `service_tier` is `flex`. Both are estimates; the
provider's invoice is the truth.

costs.csv columns: `service_tier` is the tier requested; the tier the provider reports it
served, the cache-write tokens and the median seconds per call go into the
`service_tier_served`, `cache_write_tokens` and `latency_s` columns when
`common.costs.COLUMNS` has them (schema of 2026-10-01), and into `notes` otherwise.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from common import costs

PRICE_SOURCE_DATE = "2026-09-30"
CACHE_WRITE_MULTIPLIER = 1.25
TIER_DISCOUNT = {"flex": 0.5}


@dataclass(frozen=True)
class Price:
    input: float
    cached: float
    output: float


PRICES: dict[str, Price] = {
    "gpt-6-luna": Price(0.10, 0.01, 0.50),
    "gpt-6.1-sol": Price(2.00, 0.10, 10.00),
}


def price_for(model: str) -> Price:
    """Price of a requested or returned model string (longest matching known prefix)."""
    best = None
    for name in PRICES:
        matches = model == name or model.startswith(name + "-")
        if matches and (best is None or len(name) > len(best)):
            best = name
    if best is None:
        raise KeyError(f"no price for model {model!r}; add it to harnesses.pricing.PRICES")
    return PRICES[best]


def usage_numbers(usage: dict | None) -> dict[str, int]:
    usage = usage or {}
    idet = usage.get("input_tokens_details") or {}
    odet = usage.get("output_tokens_details") or {}
    return {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cached_input_tokens": int(idet.get("cached_tokens") or 0),
        "cache_write_tokens": int(idet.get("cache_write_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "reasoning_tokens": int(odet.get("reasoning_tokens") or 0),
    }


def cost_usd(model: str, usage: dict | None, service_tier: str | None) -> tuple[float, float]:
    """(list cost, billed estimate) of one response."""
    p = price_for(model)
    u = usage_numbers(usage)
    plain = max(u["input_tokens"] - u["cached_input_tokens"] - u["cache_write_tokens"], 0)
    listed = (plain * p.input + u["cached_input_tokens"] * p.cached
              + u["cache_write_tokens"] * p.input * CACHE_WRITE_MULTIPLIER
              + u["output_tokens"] * p.output) / 1e6
    return listed, listed * TIER_DISCOUNT.get(service_tier or "", 1.0)


@dataclass
class UsageLedger:
    """Totals over one run (one costs.csv row)."""

    model_requested: str
    n_calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd_list: float = 0.0
    cost_usd_billed_est: float = 0.0
    models_returned: dict[str, int] = field(default_factory=dict)
    service_tiers: dict[str, int] = field(default_factory=dict)
    """Tiers the responses report they were served with."""
    service_tiers_requested: dict[str, int] = field(default_factory=dict)
    latencies_s: list[float] = field(default_factory=list)
    priced_as_requested: dict[str, int] = field(default_factory=dict)
    """Returned model strings with no known price, priced as the requested model."""

    def add(self, response: dict, *, requested_tier: str | None = None,
            latency_s: float | None = None) -> tuple[float, float]:
        model = response.get("model") or self.model_requested
        tier = response.get("service_tier")
        try:
            listed, billed = cost_usd(model, response.get("usage"), tier)
        except KeyError:
            # The call was made and billed: log it at the requested model's price rather than
            # losing it from costs.csv, and flag it.
            listed, billed = cost_usd(self.model_requested, response.get("usage"), tier)
            self.priced_as_requested[model] = self.priced_as_requested.get(model, 0) + 1
        u = usage_numbers(response.get("usage"))
        self.n_calls += 1
        for k, v in u.items():
            setattr(self, k, getattr(self, k) + v)
        self.cost_usd_list += listed
        self.cost_usd_billed_est += billed
        self.models_returned[model] = self.models_returned.get(model, 0) + 1
        self.service_tiers[str(tier)] = self.service_tiers.get(str(tier), 0) + 1
        if requested_tier is not None:
            self.service_tiers_requested[requested_tier] = (
                self.service_tiers_requested.get(requested_tier, 0) + 1)
        if latency_s is not None:
            self.latencies_s.append(latency_s)
        return listed, billed

    def totals(self) -> dict:
        return {k: getattr(self, k) for k in (
            "n_calls", "input_tokens", "cached_input_tokens", "cache_write_tokens",
            "output_tokens", "reasoning_tokens", "cost_usd_list", "cost_usd_billed_est")}

    def costs_row(self, *, timestamp_utc: str, run_id: str, milestone: str, experiment: str,
                  cell_or_config: str, git_commit: str, notes: str = "") -> dict:
        """One results/costs.csv row (common.costs.COLUMNS, old or 2026-10-01 schema)."""
        def joined(d: dict[str, int]) -> str:
            return ";".join(sorted(d)) if d else ""
        served = joined(self.service_tiers)
        requested = joined(self.service_tiers_requested) or served
        latency = (f"{statistics.median(self.latencies_s):.3f}" if self.latencies_s else "")
        row = {
            "timestamp_utc": timestamp_utc, "run_id": run_id, "milestone": milestone,
            "experiment": experiment, "cell_or_config": cell_or_config,
            "model_requested": self.model_requested,
            "model_returned": joined(self.models_returned), "provider": "openai",
            "api": "responses", "service_tier": requested,
            "n_calls": self.n_calls, "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens, "reasoning_tokens": self.reasoning_tokens,
            "cost_usd_list": f"{self.cost_usd_list:.6f}",
            "cost_usd_billed_est": f"{self.cost_usd_billed_est:.6f}",
            "price_source_date": PRICE_SOURCE_DATE, "git_commit": git_commit,
        }
        extra = []
        for col, value, in_notes in (
                ("service_tier_served", served, served != requested),
                ("cache_write_tokens", self.cache_write_tokens, bool(self.cache_write_tokens)),
                ("latency_s", latency, bool(latency))):
            if col in costs.COLUMNS:
                row[col] = value
            elif in_notes:
                extra.append(f"{col}={value}")
        if self.priced_as_requested:
            extra.append("priced_as_requested=" + ",".join(
                f"{m}x{n}" for m, n in sorted(self.priced_as_requested.items())))
        row["notes"] = "; ".join([notes, *extra]) if notes else "; ".join(extra)
        return row
