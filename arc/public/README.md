# arc/public: free analysis of ARC's published public-set runs

Operational slice of PLAN.md §8.1, as split by amendment §16.3. It covers how published runs
ended, seconds and cost per action, token mix, clean-run cost bounds and the eligibility
re-check. It does **not** compute H5 (per-level P(clear | reached) by harness); that slice
waits for the `PREREG.md` commit.

## Run it

```sh
# 1. Pull, or reuse the cache. One request at a time, >= 2.5 s apart, nothing re-downloaded.
PERSISTGYM_RAW_DIR=/path/to/persistgym/results/raw uv run python -m arc.public.pull
# 2. Analyse from the cache only (offline; never fetches).
PERSISTGYM_RAW_DIR=/path/to/persistgym/results/raw uv run python -m arc.public.ops
```

Nothing here needs an API key. The cache lives under `$PERSISTGYM_RAW_DIR/arc_public/`
(`pages/`, `sessions/`, `recordings/<game_id>/`; default `<repo>/results/raw`, which is
gitignored). `ops.py` writes `results/arc_public_ops/<run_id>/`: `meta.json` (with SHA-256
hashes of every cached input), `per_run.csv`, `endings_by_harness_effort.csv`,
`recordings_per_action.csv`, `clean_run_bounds.csv`, `eligibility.csv`, `lp85_example.json`
and `summary.md`.

## Modules

| File | What it does |
|---|---|
| `client.py` | Polite cached GET client for arcprize.org (throttle, User-Agent, backoff on 429/5xx, atomic cache writes, offline mode) |
| `discover.py` | Session GUIDs from the results page's embedded Next.js JSON (`group.variants` x `group.tasks.v3[].replays`) |
| `sessions.py` | Session JSON parsing and the inferred ending, with line citations to the pinned harness (`4ca00e6`) |
| `recordings.py` | Recording NDJSON parsing (schema in the module docstring) and per-action summaries |
| `premise.py` | Reads the premise check's table from `docs/background.md` §4 for comparison |
| `pull.py`, `ops.py` | The two entry points above |
