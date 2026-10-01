import pytest

from persistgym.config import GeneratorConfig
from persistgym.episode import ALL_CELLS, VARIANTS
from persistgym.render import generate

# Small volume for fast tests: same W/v ratio as the defaults (far gap 16 steps).
SMALL = GeneratorConfig(W_tokens=6_400, v_tokens=400, assumed_max_reply_tokens=200)


@pytest.fixture(scope="session")
def small_cfg() -> GeneratorConfig:
    return SMALL


@pytest.fixture(scope="session")
def small_rendered():
    """10 templates x 8 cells x 3 variants at the small volume."""
    return list(generate("main", range(10), SMALL, ALL_CELLS, VARIANTS))


@pytest.fixture(scope="session")
def small_eps(small_rendered):
    return [ep for _, eps in small_rendered for ep in eps]


@pytest.fixture(scope="session")
def default_rendered():
    """2 templates x 8 cells, base and restated, at the default W=24000, v=1500."""
    return list(generate("main", range(2), GeneratorConfig(), ALL_CELLS, ("base", "restated")))


@pytest.fixture(scope="session")
def default_eps(default_rendered):
    return [ep for _, eps in default_rendered for ep in eps]


def pick(eps, cell_id: str, variant: str = "base", template_index: int = 0):
    tid = f"main-{template_index:06d}"
    return next(e for e in eps if e.cell.id == cell_id and e.variant == variant
                and e.template_id == tid)
