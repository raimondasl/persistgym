"""Golden fixture of the default config's episodes (generator 0.3.0).

`golden_0_3_0.json` holds the sha256 of every episode (`episode.content_sha256`: canonical
JSON without `generator_version`) rendered with the default `GeneratorConfig()` by generator
0.3.0, before any change of generator 0.4.0: validity templates 0-19, pilot 0-3 and main 0-9,
each in the 8 task cells and the 3 variants. luna's validity runs, pilots and spot-check
package used these episodes, so later generator versions must render them byte for byte
(apart from the version string) under the default config.

The fixture was written once, at generator 0.3.0, by

    uv run python -m persistgym.tests.test_golden

which refuses to overwrite it.
"""

import json
import sys
from pathlib import Path

from common.runmeta import config_hash
from persistgym import spotcheck
from persistgym.config import GENERATOR_VERSION, GeneratorConfig
from persistgym.episode import ALL_CELLS, VARIANTS, content_sha256
from persistgym.render import generate

GOLDEN = Path(__file__).resolve().with_name("golden_0_3_0.json")
SETS = (("validity", 20), ("pilot", 4), ("main", 10))
DEFAULT_HASH = "3d6bc648eaa9b9e843fe6e70060495cd197630b0f2d585e66b3cd280b7a3968b"


def digests(cfg: GeneratorConfig) -> dict[str, str]:
    out = {}
    for split, n in SETS:
        for _, eps in generate(split, range(n), cfg, ALL_CELLS, VARIANTS):
            for ep in eps:
                out[ep.episode_id] = content_sha256(ep)
    return out


def spotcheck_digest(cfg: GeneratorConfig) -> str:
    """`spotcheck.episodes_sha256` of the luna package's episodes: the base variant of
    validity templates 0-19, by task cell, then by template."""
    eps = [e for _, es in generate("validity", range(20), cfg, ALL_CELLS, ("base",)) for e in es]
    ordered = [e for c in ALL_CELLS for e in eps if e.cell == c]
    return spotcheck.episodes_sha256(ordered)


def test_default_config_hash_is_luna_s():
    assert config_hash(GeneratorConfig().to_dict()) == DEFAULT_HASH


def test_default_renders_equal_the_0_3_0_golden_fixture():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert golden["generator_version"] == "0.3.0"
    assert golden["config_hash"] == DEFAULT_HASH
    assert golden["sets"] == [list(s) for s in SETS]
    assert len(golden["episodes"]) == (20 + 4 + 10) * 8 * 3
    got = digests(GeneratorConfig())
    differ = sorted(k for k in golden["episodes"] if got.get(k) != golden["episodes"][k])
    assert not differ and set(got) == set(golden["episodes"]), differ[:5]


def test_spotcheck_digest_of_luna_s_package_is_pinned():
    assert spotcheck_digest(GeneratorConfig()) == spotcheck.GOLDEN_0_3_0_SPOTCHECK_SHA256


def _write() -> int:
    if GOLDEN.exists():
        print(f"refused: {GOLDEN} exists; the fixture is written once", file=sys.stderr)
        return 2
    cfg = GeneratorConfig()
    doc = {"generator_version": GENERATOR_VERSION, "config_hash": config_hash(cfg.to_dict()),
           "sets": [list(s) for s in SETS], "episodes": digests(cfg)}
    GOLDEN.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                      newline="\n")
    print(f"wrote {len(doc['episodes'])} digests to {GOLDEN}")
    print(f"spot-check package digest: {spotcheck_digest(cfg)}")
    return 0


if __name__ == "__main__":
    sys.exit(_write())
