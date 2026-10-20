# persistgym: when the harness decides success

Code, pre-registration and data for the preprint *When the harness decides success: state that
cannot be re-observed* (Raimondas Lencevicius, 2026), [arXiv:2610.26632](https://arxiv.org/abs/2610.26632).
The tag `preprint-v1` marks the state of the repository that its v1 describes.

An agent harness decides what a language model sees across turns: it drops old turns, summarizes
them, or replays the model's own earlier reasoning. The study asks when these choices change whether
an agent succeeds, not only what it costs. It has two parts:

- **PersistGym-lite,** a generated environment in which a fact needed late in an episode is either
  shown or derived, and either recoverable by a lookup or not. A pre-registered probe compares a
  full-history harness with a truncated window on a low-cost reasoning model, with a
  pre-registered replication on one model from a second provider.
- **A decomposition of ARC-AGI-3's harness gap,** the score difference between the benchmark's
  Standard and Provider Adapter harnesses, one component at a time, for one model on four games:
  the loss policy, the note-taking instruction and native reasoning replay.

The paper states what the results do and do not show. In particular, the ARC decomposition rests
on one counted run per configuration and game.

## What is here

| Path | Contents |
|---|---|
| `PREREG.md` | The pre-registration: hypotheses, predictions, thresholds and analyses, frozen on 2026-10-01 before the first paid run (PR #4), with dated amendments R1 to R8 in §17 |
| `PLAN.md` | The study plan: designs, milestones, gates, budget and kill criteria, with the amendments that cut its scope |
| `results/decisions.md` | The decisions log: every gate, approval, ruling, deviation and correction, in order |
| `results/costs.csv` | The cost ledger: one row per paid call batch (tokens, list and billed-estimate cost) |
| `results/<experiment>/<run>/` | Per-run metadata (`meta.json`), scorecards and summaries; each analysis output folder records the git commit and the inputs it read |
| `persistgym/` | The PersistGym-lite generator, programmatic oracle and validity checks |
| `harnesses/` | The PersistGym-lite harness cells (full history, window, notes, summary) and payload snapshot tests |
| `arc/` | The pinned ARC-AGI-3 harness (`arc/upstream`, a submodule of `arcprize/arc-agi-3-benchmarking` at `4ca00e6`), our patch series in `arc/patches/`, the configuration freeze record and the guarded launcher |
| `analysis/` | The statistics (bootstrap, GLM, Bayesian check, power simulation) and the paper's figures |
| `docs/` | Background facts with sources, and the premise checks behind the plan |
| `CLAUDE.md` | The working rules for the AI coding assistant used in this project (see below) |

Raw model transcripts (`results/raw/`) are not in the repository. Most analyses read only
committed files. Two read the transcripts as well: the carried-fact accounting in
`analysis/persistgym_h1h3.py` and the compaction analysis in `analysis/arc_compaction.py`.

## Reproducing the analyses

Python is managed with [uv](https://docs.astral.sh/uv/).

```bash
git clone --recurse-submodules https://github.com/raimondasl/persistgym
cd persistgym
uv sync
uv run pytest -q
```

The tests and the analyses need no API key and make no model call. For example, these regenerate
the ARC decomposition, the level-depth analysis and the figures from committed outputs:

```bash
uv run python -m analysis.arc_h4
uv run python -m analysis.arc_h5
uv run python -m analysis.figures
```

Each module's docstring gives its inputs and options. New paid runs need your own API keys in a
local `.env` (see `.env.example`) and pass through launchers that refuse to run without a
recorded approval and a frozen pre-registration.

## How this was built

The code, analyses, adversarial reviews and drafts were produced with an AI coding assistant
(Claude Code) under the researcher's direction; `CLAUDE.md` holds its working rules, and commits
carry a `Co-Authored-By` line. The researcher designed the study, made every decision recorded in
`results/decisions.md` and approved every paid run.

This is a one-off study of harness mechanisms, not a model leaderboard: figures plot effects
against task properties, not models against each other.

## Citing

```bibtex
@misc{lencevicius2026harness,
  title         = {When the harness decides success: state that cannot be re-observed},
  author        = {Lencevicius, Raimondas},
  year          = {2026},
  eprint        = {2610.26632},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2610.26632}
}
```

## License

MIT (see `LICENSE`). The ARC-AGI-3 harness in `arc/upstream` is ARC Prize Foundation's, under its
own MIT license.
