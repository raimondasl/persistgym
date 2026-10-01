import json

import pytest

from arc.public.discover import flight_text, group_object, harness_of_variant, published_runs

G1 = "11111111-1111-4111-8111-111111111111"
G2 = "22222222-2222-4222-8222-222222222222"
G3 = "33333333-3333-4333-8333-333333333333"
G4 = "44444444-4444-4444-8444-444444444444"

GROUP = {
    "group": {
        "id": "google-gemini-3-8-flash",
        "variants": [
            {"id": "high", "label": "High", "reasoningLevel": "high"},
            {"id": "provider-adapter-high", "label": "High (Provider Adapter)",
             "reasoningLevel": "high"},
        ],
        "tasks": {"v3": [
            {"name": "LP85", "scores": [0.7777, 1],
             "replays": [f"https://arcprize.org/replay/{G1}", f"https://arcprize.org/replay/{G2}"]},
            {"name": "FT09", "scores": [0.1428, 1],
             "replays": [f"https://arcprize.org/replay/{G3}", f"https://arcprize.org/replay/{G4}"]},
        ]},
    },
    "comparisons": [],
}


def page(chunks: list[str]) -> str:
    """Mimic Next.js: the flight text is split across several push() script tags."""
    scripts = ["<script>(self.__next_f=self.__next_f||[]).push([0])</script>"]
    for c in chunks:
        scripts.append(f"<script>self.__next_f.push({json.dumps([1, c])})</script>")
    return "<html><body>" + "".join(scripts) + "</body></html>"


def fixture_html() -> str:
    text = '1f:["$","$L1f",null,' + json.dumps(GROUP) + "]\n20:[]\n"
    cut = len(text) // 2
    return page([text[:cut], text[cut:]])


def test_flight_text_joins_chunks():
    t = flight_text(fixture_html())
    assert '{"group":' in t and t.endswith("20:[]\n")


def test_group_object_and_runs():
    html = fixture_html()
    assert group_object(html)["id"] == "google-gemini-3-8-flash"
    runs = published_runs(html)
    assert [(r.game, r.harness, r.effort, r.guid) for r in runs] == [
        ("LP85", "standard", "high", G1), ("LP85", "provider_adapter", "high", G2),
        ("FT09", "standard", "high", G3), ("FT09", "provider_adapter", "high", G4)]
    assert runs[0].page_score == pytest.approx(0.7777)


def test_misaligned_replays_raise():
    bad = json.loads(json.dumps(GROUP))
    bad["group"]["tasks"]["v3"][0]["replays"].pop()
    html = page(['x:["$","$L1f",null,' + json.dumps(bad) + "]"])
    with pytest.raises(ValueError):
        published_runs(html)


def test_no_flight_data_raises():
    with pytest.raises(ValueError):
        flight_text("<html></html>")


def test_harness_of_variant():
    assert harness_of_variant("provider-adapter-low") == "provider_adapter"
    assert harness_of_variant("medium") == "standard"
