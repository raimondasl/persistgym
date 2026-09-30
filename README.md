# persistgym: when does the agent harness matter?

The harness around a model can move agent scores a lot on some benchmarks and hardly at all on others. On ARC-AGI-3, ARC Prize's two official harnesses gave GPT-6 Astra 62.7% and 99.95% ([ARC blog](https://arcprize.org/blog/astra)). On coding agents, HarnessTax found the harness moved success by only about ±2-5pp but cost by up to 5x ([Arena](https://arena.ai/blog/coding-agents-harness-tax)). This project tests one explanation for the difference: the harness changes *success* when the state an agent needs is **derived** (it exists only in the agent's reasoning or notes) and **cannot be re-observed**, and the harness throws it away. When the state can be re-read from the environment, harness differences should mostly show up as *cost*. The project has three parts:
- **PersistGym**, a small generated environment that varies these properties one at a time.
- **An ARC path decomposition** that measures how much of ARC's Standard-to-Adapter gap on Gemini 3.8 Flash comes from each harness component.
- **StateCarry**, a provider-neutral add-on for ARC's Standard harness, built from what the first two parts show and meant to recover most of the Adapter's advantage.

## Status (2026-09-30)
- **Planning only.** There is no code and no paid run yet. This repo was spun out of idea `I-20260929-06` in the researcher's `ai-research` scouting repo (card: `runs/2026-09-29/ideas/I-20260929-06-when-does-the-harness-matter-a-state-persistence.md`), and selected on 2026-09-30. Everything needed to continue is in this repo; the scouting repo is history only.
- Three independent premise checks came back **go, narrowed**. The plan in `PLAN.md` already includes their corrections; `docs/premise-check.md` records what they found and how the plan responds.
- **Next step:** milestone M0 in `PLAN.md` (Oct 1-7): freeze the pre-registration, pin and patch the ARC harness, run the free analysis of ARC's published runs, and run the toggle and cost pilots.

## Where to start
1. `PLAN.md`: research question, hypotheses, designs, milestones with go/no-go gates, budget, kill criteria, venues.
2. `docs/background.md`: verified facts (ARC numbers, harness code differences, API replay behaviour, prices) and the related-work table.
3. `docs/premise-check.md`: what the three checks found, where they disagreed, and how the plan answers each objection.
4. `CLAUDE.md`: working rules for Claude Code sessions in this repo.

## Layout
Current:
```
README.md            this file
PLAN.md              the plan (source of truth for scope, gates and budget)
CLAUDE.md            instructions for Claude Code sessions
docs/background.md   verified facts and related work
docs/premise-check.md  summary of the three premise checks
.gitignore
```
Planned (created as the milestones need them; see `CLAUDE.md`):
```
PREREG.md            frozen hypotheses and analysis plan (M0, before any paid run)
persistgym/          task generator, programmatic oracle, survival calculator
harnesses/           harness cells for PersistGym, with payload snapshot tests
arc/                 notes and patches for the pinned fork of arcprize/arc-agi-3-benchmarking
statecarry/          the builder component (phase 2)
analysis/            statistics and figures
results/             run metadata, summaries and costs.csv (results/raw/ is gitignored)
drafts/              post and paper drafts (gitignored; the researcher reviews before anything is public)
```

## Scope guardrails
- This is a one-off study of harness **mechanisms**, not a model leaderboard. Figures plot effects against task properties (recoverable, derived, distance), not models against each other. Vendors are named neutrally. There is no standing dashboard.
- Reported runs use API keys with pinned model versions, never consumer subscriptions.
- Nothing is posted publicly (preprint, blog, upstream PR, social) until the researcher has reviewed the exact text. The researcher posts from their own accounts.
