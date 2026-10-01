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
"""

from __future__ import annotations

from dataclasses import dataclass, field

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

    def add(self, response: dict) -> tuple[float, float]:
        model = response.get("model") or self.model_requested
        tier = response.get("service_tier")
        listed, billed = cost_usd(model, response.get("usage"), tier)
        u = usage_numbers(response.get("usage"))
        self.n_calls += 1
        for k, v in u.items():
            setattr(self, k, getattr(self, k) + v)
        self.cost_usd_list += listed
        self.cost_usd_billed_est += billed
        self.models_returned[model] = self.models_returned.get(model, 0) + 1
        self.service_tiers[str(tier)] = self.service_tiers.get(str(tier), 0) + 1
        return listed, billed

    def totals(self) -> dict:
        return {k: getattr(self, k) for k in (
            "n_calls", "input_tokens", "cached_input_tokens", "cache_write_tokens",
            "output_tokens", "reasoning_tokens", "cost_usd_list", "cost_usd_billed_est")}

    def costs_row(self, *, timestamp_utc: str, run_id: str, milestone: str, experiment: str,
                  cell_or_config: str, git_commit: str, notes: str = "") -> dict:
        """One results/costs.csv row (common.costs.COLUMNS)."""
        def joined(d: dict[str, int]) -> str:
            return ";".join(sorted(d)) if d else ""
        return {
            "timestamp_utc": timestamp_utc, "run_id": run_id, "milestone": milestone,
            "experiment": experiment, "cell_or_config": cell_or_config,
            "model_requested": self.model_requested,
            "model_returned": joined(self.models_returned), "provider": "openai",
            "api": "responses", "service_tier": joined(self.service_tiers),
            "n_calls": self.n_calls, "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens, "reasoning_tokens": self.reasoning_tokens,
            "cost_usd_list": f"{self.cost_usd_list:.6f}",
            "cost_usd_billed_est": f"{self.cost_usd_billed_est:.6f}",
            "price_source_date": PRICE_SOURCE_DATE, "git_commit": git_commit,
            "notes": notes + (f"; cache_write_tokens={self.cache_write_tokens}"
                              if self.cache_write_tokens else ""),
        }
