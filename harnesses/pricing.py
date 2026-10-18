"""Prices and a per-run usage ledger that produces the results/costs.csv row.

Prices (USD per million tokens):
* checked 2026-09-30 (PLAN.md §12, docs/background.md §6):
  * gpt-6-luna: $0.10 input / $0.01 cached / $0.50 output
    (https://developers.openai.com/api/docs/pricing)
  * gpt-6.1-sol: $2.00 / $0.10 / $10.00 (same source)
  * Flex: 50% off (https://developers.openai.com/api/docs/guides/flex-processing)
  * Cache writes: "1.25x the standard, uncached input-token rate" on GPT-5.6 and later
    (https://developers.openai.com/api/docs/guides/prompt-caching; PLAN §16.1)
* checked 2026-10-17 (https://platform.claude.com/docs/en/about-claude/pricing, "Long context
  pricing"): claude-haiku-5-5 is priced per request by its prompt size P = input tokens +
  cache-read tokens + cache-write tokens. P <= 100,000: $0.10 input, $0.125 5-minute cache
  write, $0.01 cache read, $0.50 output; P > 100,000: $0.50, $0.625, $0.05 and $2.50, for every
  token of that request, output included. A 1-hour cache write costs 2x input (never
  requested here). No Flex tier: the billed estimate equals the list cost.

`cost_usd_list` is the standard-tier price of the usage; `cost_usd_billed_est` applies the
Flex discount when an OpenAI response's echoed `service_tier` is `flex`. Both are estimates;
the provider's invoice is the truth.

Usage is read in one meaning on both APIs (`usage_numbers` for OpenAI's Responses API,
`messages_usage_numbers` for Anthropic's Messages API): `input_tokens` counts every input
token, cached ones included (Anthropic reports them apart, so they are added back);
`cached_input_tokens` are cache reads; `cache_write_tokens` cache writes; `output_tokens`
include reasoning (thinking) tokens; `reasoning_tokens` is None when the provider does not
report them, never 0.

costs.csv columns: `service_tier` is the tier requested; the tier the provider reports it
served, the cache-write tokens and the median seconds per call go into the
`service_tier_served`, `cache_write_tokens` and `latency_s` columns when
`common.costs.COLUMNS` has them (schema of 2026-10-01), and into `notes` otherwise.
`provider`, `api` and `price_source_date` are the requested model's (`Price`). For a model
priced by prompt size, the notes give the run's largest prompt and how many calls went over
the threshold (`max_prompt_tokens=`, `calls_over_<threshold>=`).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from common import costs

PRICE_SOURCE_DATE = "2026-09-30"
"""The source date of the OpenAI prices (each `Price` carries its own)."""
CACHE_WRITE_MULTIPLIER = 1.25
"""OpenAI's cache writes, and Anthropic's 5-minute ones: 1.25x the input price."""
CACHE_WRITE_1H_MULTIPLIER = 2.0
"""Anthropic's 1-hour cache writes: 2x the input price (never requested: `harnesses.wire`
sends 5-minute caching only; priced right should one ever be billed)."""
TIER_DISCOUNT = {"flex": 0.5}


@dataclass(frozen=True)
class Price:
    input: float
    cached: float
    output: float
    provider: str = "openai"
    api: str = "responses"
    source_date: str = PRICE_SOURCE_DATE
    long_threshold: int | None = None
    """Prompt size (input + cache reads + cache writes) above which a request is priced at
    the `long` card, every token of it; None: one card."""
    long: tuple[float, float, float] | None = None
    """(input, cached, output) above `long_threshold`."""

    def card(self, prompt_tokens: int) -> tuple[float, float, float]:
        """(input, cached, output) of a request with this prompt size."""
        if self.long_threshold is not None and prompt_tokens > self.long_threshold:
            return self.long
        return self.input, self.cached, self.output

    def worst_card(self) -> tuple[float, float, float]:
        """The dearest card: what a bound on one call's cost must use."""
        return self.long if self.long is not None else (self.input, self.cached, self.output)


HAIKU_PRICE_SOURCE_DATE = "2026-10-17"
HAIKU_LONG_THRESHOLD = 100_000

PRICES: dict[str, Price] = {
    "gpt-6-luna": Price(0.10, 0.01, 0.50),
    "gpt-6.1-sol": Price(2.00, 0.10, 10.00),
    "claude-haiku-5-5": Price(0.10, 0.01, 0.50, provider="anthropic", api="messages",
                              source_date=HAIKU_PRICE_SOURCE_DATE,
                              long_threshold=HAIKU_LONG_THRESHOLD, long=(0.50, 0.05, 2.50)),
}


_UNPRICED = Price(0.0, 0.0, 0.0)


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
    """OpenAI Responses usage: `input_tokens` already counts cached tokens."""
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


def messages_usage_numbers(usage: dict | None) -> dict[str, int | None]:
    """Anthropic Messages usage in `usage_numbers`' meanings: `input_tokens` =
    `input_tokens` (uncached only, on this API) + `cache_read_input_tokens` +
    `cache_creation_input_tokens`, the prompt size P that also picks the price card;
    cached = cache reads; cache writes = cache creation; `output_tokens` as reported
    (thinking included); `reasoning_tokens` = `output_tokens_details.thinking_tokens`, or
    None when the response does not report it."""
    usage = usage or {}
    read = int(usage.get("cache_read_input_tokens") or 0)
    write = int(usage.get("cache_creation_input_tokens") or 0)
    thinking = (usage.get("output_tokens_details") or {}).get("thinking_tokens")
    return {
        "input_tokens": int(usage.get("input_tokens") or 0) + read + write,
        "cached_input_tokens": read,
        "cache_write_tokens": write,
        "output_tokens": int(usage.get("output_tokens") or 0),
        "reasoning_tokens": None if thinking is None else int(thinking),
    }


def normalized_usage(api: str, usage: dict | None) -> dict:
    """A response's usage in one meaning, read in the shape of its `api`."""
    return messages_usage_numbers(usage) if api == "messages" else usage_numbers(usage)


def served_tier(api: str, response: dict) -> str | None:
    """The tier a response says it was served on: OpenAI's top-level `service_tier`,
    Anthropic's `usage.service_tier`."""
    if api == "messages":
        return (response.get("usage") or {}).get("service_tier")
    return response.get("service_tier")


def add_counts(total: dict, numbers: dict) -> dict:
    """Add one call's usage numbers to `total` (in place, and returned), key by key. A
    count the provider did not report (None) makes its total unknown (None): a total of the
    calls that did report it would read as the run's."""
    for k, v in numbers.items():
        before = total.get(k, 0)
        total[k] = None if before is None or v is None else before + v
    return total


def cost_usd(model: str, usage: dict | None, service_tier: str | None) -> tuple[float, float]:
    """(list cost, billed estimate) of one response. A model priced by prompt size is priced
    at the card its prompt size picks; its billed estimate is the list cost (no Flex)."""
    p = price_for(model)
    u = normalized_usage(p.api, usage)
    inp, cached, out = p.card(u["input_tokens"])
    plain = max(u["input_tokens"] - u["cached_input_tokens"] - u["cache_write_tokens"], 0)
    listed = (plain * inp + u["cached_input_tokens"] * cached
              + u["cache_write_tokens"] * inp * CACHE_WRITE_MULTIPLIER
              + u["output_tokens"] * out) / 1e6
    if p.api == "messages":
        one_hour = int(((usage or {}).get("cache_creation") or {})
                       .get("ephemeral_1h_input_tokens") or 0)
        listed += one_hour * inp * (CACHE_WRITE_1H_MULTIPLIER - CACHE_WRITE_MULTIPLIER) / 1e6
        return listed, listed
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
    reasoning_tokens: int | None = 0
    """None once a call did not report its reasoning tokens (`add_counts`)."""
    cost_usd_list: float = 0.0
    cost_usd_billed_est: float = 0.0
    models_returned: dict[str, int] = field(default_factory=dict)
    service_tiers: dict[str, int] = field(default_factory=dict)
    """Tiers the responses report they were served with."""
    service_tiers_requested: dict[str, int] = field(default_factory=dict)
    latencies_s: list[float] = field(default_factory=list)
    priced_as_requested: dict[str, int] = field(default_factory=dict)
    """Returned model strings with no known price, priced as the requested model."""
    max_prompt_tokens: int = 0
    """The largest prompt size P (input + cache reads + cache writes) of a call."""
    calls_over_threshold: int = 0
    """Calls whose prompt size passed the price's `long_threshold` (the dearer card)."""

    @property
    def price(self) -> Price:
        """The requested model's price; an unpriced model string (which no transport sends:
        they refuse it) is read as an OpenAI one, as before prices carried their API."""
        try:
            return price_for(self.model_requested)
        except KeyError:
            return _UNPRICED

    def add(self, response: dict, *, requested_tier: str | None = None,
            latency_s: float | None = None) -> tuple[float, float]:
        model = response.get("model") or self.model_requested
        api = self.price.api
        tier = served_tier(api, response)
        try:
            listed, billed = cost_usd(model, response.get("usage"), tier)
        except KeyError:
            # The call was made and billed: log it at the requested model's price rather than
            # losing it from costs.csv, and flag it.
            listed, billed = cost_usd(self.model_requested, response.get("usage"), tier)
            self.priced_as_requested[model] = self.priced_as_requested.get(model, 0) + 1
        u = normalized_usage(api, response.get("usage"))
        self.n_calls += 1
        for k, v in add_counts({k: getattr(self, k) for k in u}, u).items():
            setattr(self, k, v)
        self.cost_usd_list += listed
        self.cost_usd_billed_est += billed
        self.models_returned[model] = self.models_returned.get(model, 0) + 1
        self.service_tiers[str(tier)] = self.service_tiers.get(str(tier), 0) + 1
        if requested_tier is not None:
            self.service_tiers_requested[requested_tier] = (
                self.service_tiers_requested.get(requested_tier, 0) + 1)
        if latency_s is not None:
            self.latencies_s.append(latency_s)
        self.max_prompt_tokens = max(self.max_prompt_tokens, u["input_tokens"])
        threshold = self.price.long_threshold
        self.calls_over_threshold += threshold is not None and u["input_tokens"] > threshold
        return listed, billed

    def totals(self) -> dict:
        return {k: getattr(self, k) for k in (
            "n_calls", "input_tokens", "cached_input_tokens", "cache_write_tokens",
            "output_tokens", "reasoning_tokens", "cost_usd_list", "cost_usd_billed_est")}

    def prompt_size(self) -> dict | None:
        """For a model priced by prompt size: the run's largest prompt and how many calls
        passed the threshold; None for one card."""
        threshold = self.price.long_threshold
        if threshold is None:
            return None
        return {"threshold": threshold, "max_prompt_tokens": self.max_prompt_tokens,
                "calls_over_threshold": self.calls_over_threshold}

    def costs_row(self, *, timestamp_utc: str, run_id: str, milestone: str, experiment: str,
                  cell_or_config: str, git_commit: str, notes: str = "") -> dict:
        """One results/costs.csv row (common.costs.COLUMNS, old or 2026-10-01 schema)."""
        def joined(d: dict[str, int]) -> str:
            return ";".join(sorted(d)) if d else ""
        price = self.price
        served = joined(self.service_tiers)
        requested = joined(self.service_tiers_requested) or served
        latency = (f"{statistics.median(self.latencies_s):.3f}" if self.latencies_s else "")
        row = {
            "timestamp_utc": timestamp_utc, "run_id": run_id, "milestone": milestone,
            "experiment": experiment, "cell_or_config": cell_or_config,
            "model_requested": self.model_requested,
            "model_returned": joined(self.models_returned), "provider": price.provider,
            "api": price.api, "service_tier": requested,
            "n_calls": self.n_calls, "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": "" if self.reasoning_tokens is None else self.reasoning_tokens,
            "cost_usd_list": f"{self.cost_usd_list:.6f}",
            "cost_usd_billed_est": f"{self.cost_usd_billed_est:.6f}",
            "price_source_date": price.source_date, "git_commit": git_commit,
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
        size = self.prompt_size()
        if size is not None:
            extra.append(f"max_prompt_tokens={size['max_prompt_tokens']}; "
                         f"calls_over_{size['threshold']}={size['calls_over_threshold']}")
        if self.reasoning_tokens is None:
            extra.append("reasoning_tokens not reported by the provider")
        row["notes"] = "; ".join([notes, *extra]) if notes else "; ".join(extra)
        return row
