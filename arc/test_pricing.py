"""The Gemini price table and the cost of recorded usage (arc/pricing.py)."""

from __future__ import annotations

import csv
from datetime import date

import pytest

from arc import apply_patches as ap
from arc import config_hash as freeze
from arc import pricing
from arc.pricing import Usage

REPO = ap.REPO_ROOT


def test_table_matches_the_cost_model_inputs():
    rows = list(csv.DictReader((REPO / "analysis" / "data" / "prices.csv").open(
        encoding="utf-8")))
    (row,) = [r for r in rows if (r["provider"], r["model"], r["tier"])
              == ("google", "gemini-3.8-flash", "standard")]
    p = pricing.PRICES[("gemini-3.8-flash", "standard")]

    assert (p.input, p.cached, p.output) == (float(row["input_usd_per_m"]),
                                             float(row["cached_usd_per_m"]),
                                             float(row["output_usd_per_m"]))
    assert p.valid_through.isoformat() == row["valid_to"]
    assert pricing.PRICE_SOURCE_URL == row["source_url"]
    assert pricing.PRICE_SOURCE_DATE == row["checked"]


def test_table_matches_the_frozen_profiles_list_prices():
    record = freeze.load_record()
    p = pricing.price_for("gemini-3.8-flash")
    for entry in record["profiles"].values():
        assert entry["config"]["pricing"] == {"input": p.input, "output": p.output}
        assert entry["config"]["request"]["model"] == "gemini-3.8-flash"


def test_price_for_refuses_unknown_models_tiers_and_dates():
    assert pricing.price_for("gemini-3.8-flash", on=date(2026, 12, 31)).input == 0.75
    with pytest.raises(pricing.PriceError, match="valid through 2026-12-31"):
        pricing.price_for("gemini-3.8-flash", on=date(2027, 1, 1))
    with pytest.raises(pricing.PriceError, match="no price"):
        pricing.price_for("gemini-3.8-flash", "flex")
    with pytest.raises(pricing.PriceError, match="no price"):
        pricing.price_for("gemini-3.9-pro")


def test_list_ignores_the_cache_and_billed_prices_cached_input():
    u = Usage(prompt_tokens=1_000_000, cached_tokens=400_000, completion_tokens=100_000,
              reasoning_tokens=80_000)
    listed, billed = pricing.cost_usd(u, pricing.price_for("gemini-3.8-flash"))

    assert listed == pytest.approx(0.75 + 0.375)                      # 1M in, 0.1M out
    assert billed == pytest.approx(0.6 * 0.75 + 0.4 * 0.075 + 0.375)
    assert billed < listed


def test_usage_from_harness_records():
    record = {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17,
              "reasoning_tokens": 5, "cached_tokens": 4, "cache_write_tokens": 0,
              "cost": 0.0, "cost_details": {}}
    assert Usage.from_record(record) == Usage(10, 4, 7, 5)
    assert Usage.from_record(None) == Usage()
    assert Usage(1, 0, 2, 1) + Usage(3, 1, 4, 0) == Usage(4, 1, 6, 1)
    assert Usage(10, 4, 7, 5).minus(Usage(3, 5, 7, 1)) == Usage(7, 0, 0, 4)


@pytest.mark.parametrize("bad", [
    {"prompt_tokens": -1}, {"prompt_tokens": 1.5}, {"prompt_tokens": True},
    {"prompt_tokens": "3"}, {"prompt_tokens": 2, "cached_tokens": 3},
])
def test_usage_rejects_bad_records(bad):
    with pytest.raises(pricing.PriceError):
        Usage.from_record(bad)
