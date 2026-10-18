"""H1 and H3 on gpt-6-luna's PersistGym main sweep, as pre-registered (PREREG §3 H1, §3 H3,
§2.8, §2.9, §9.1-§9.5, §13 and §15; amendments R2 change 3 and R6 changes 1, 6 and 9); and,
with ``--model claude-haiku-5-5``, amendment R8's replication of both on claude-haiku-5-5
(§17.8; "A second model" below).

Run: ``uv run python -m analysis.persistgym_h1h3 --run RUN_ID [--run RUN_ID ...]
[--rerun RUN=ORIGINAL ...] [--sweep-closed REF] [--results-root DIR] [--raw-root DIR]
[--no-write] [--boot N] [--no-bayes] [--allow-incomplete] [--model MODEL] [--experiment NAME]
[--power-path CSV]`` ($0: it reads files only). It writes
``<results root>/persistgym_h1h3/<UTC>/h1h3.json``, ``summary.md`` and ``meta.json``, and prints
the summary. It was written and tested on synthetic data only, before any outcome of the sweep
was read (the researcher's blinding rule of 2026-10-10), and revised after two reviews of the
code (2026-10-10), still blind. It was then changed after its FINAL output was read: items A-C
at the end of the readings below (`CHANGED_AFTER_FINAL`), each reported with the output before
it.

**Inputs.**

* The runs named with ``--run`` (harnesses/DESIGN.md §7.8: "the analysis's input list should
  name every run it reads"): folders of ``<results root>/persistgym/`` whose ``meta.json`` is a
  gpt-6-luna run (the requested model or a dated snapshot of it, `registered.model_family`) of
  experiment ``persistgym`` on the default generator config (``config.generator_config_hashes``
  is exactly ``[registered.LUNA_GENERATOR_HASH]``). A named run that is not found there, or is
  not such a run, is refused. Every other folder is listed as skipped, with the reason; a luna
  run that is not named is skipped as "not in the input list", so a forgotten run shows. Without
  ``--run`` every luna run found is read, and the output is PROVISIONAL. A run is one of the 6
  run kinds of R6 change 1 (`KINDS`): F-0, W-0, W-n-0 and Σ-n-0 on base episodes, F-0 on the
  restated-at-need control, and the single-turn control, each at ``repeat_index`` 0 or 1 (a
  record without the field is repeat 0).
* ``<results root>/draw/*/draw.json`` for SEED (D15); the bootstrap RNG is
  ``numpy.random.default_rng(SEED + 10)`` (§9.1).
* The raw transcripts of the window-cell runs,
  ``<raw root>/persistgym/<run_id>/transcript.jsonl.gz`` (default raw root:
  ``<results root>/raw``), for §2.8's accounting check only.
* The committed luna power run ``results/power_sim/20261010T030442Z/luna_decision.csv``,
  for the achieved power quoted with the results (§9.4).

**Runtime.** The §2.8 replay reads every line of every window-cell transcript. luna's W-0 and
W-n-0 transcripts are about 700-760 MB each (gzip), plus about 70 MB per repeat-1 run, so the
replay alone takes many minutes per run (tens of minutes in all is normal). The Bayesian
sensitivity fit (below) adds a few minutes; ``--no-bayes`` skips it (PROVISIONAL).

**Episode keys, re-runs and continuations** (harnesses/DESIGN.md §7.8, §7.9; §13). A record is
keyed on (harness cell, ``episode_id``, ``repeat_index``): every harness cell plays the same
episode ids, so §7.8's key is applied within a harness cell. Runs are read in the order they
started (``started_utc``), records in file order. Per key the first *final* record counts:
``DONE``, ``MAX_TURNS``, ``REASONING_CONTEXT_MISMATCH``, ``REASONING_EFFORT_MISMATCH`` (and
``AGENT_ERROR``, see the readings below); ``API_ERROR``, ``COST_CAP``, ``RUN_STOPPED`` and
``ERROR:*`` are not final. Every later record of the key is dropped and listed. A key with two
``API_ERROR`` records before its first final one is excluded (§13: a second transport failure),
and so is one with two and no final record. A key with no final record and fewer than two
``API_ERROR`` records is *pending* (its re-run or continuation has not landed), unless the sweep
is closed (``--sweep-closed``, below). A key that appears in a later run is accepted only if
that run is declared, with ``--rerun RUN=ORIGINAL``, as a re-run or continuation of a run that
already holds the key; the declarations must match the runs listed in ``results/decisions.md``
(§7.8: no tool records the link). An undeclared duplicate is refused in any case (exit 2), to
be resolved by hand.

**A closed sweep** (``--sweep-closed REF``; DESIGN §7.8's last rule). REF names the entry of
``results/decisions.md`` in which the researcher closed the sweep (no further run will be made);
it is printed in the summary and written to ``meta.json``. Then a key with no final record is
excluded, as §7.8 says ("and so is a key with no final record at all (reported with its last
ending)"), and counted per cell by its last ending; a repeat-0 key of templates 0 to T - 1 that
no run played is excluded too and counted per cell ("never played"). Both are listed in the
summary's Deviations section (§13: deviations are listed in every write-up), and the output
can be FINAL. Two cases still refuse: a key whose last record is a single ``API_ERROR``, whose
§13 re-run has not been made (§13 re-runs it once; the block's approval covers it), and a run
kind with no record at all on templates 0 to T - 1 (a missing run, not a closed sweep).

**Exclusions** (§13; R2 change 3, §17.2). A counted record is excluded when the runner marked
it ``excluded``, ended on an echo mismatch, or (a check of our own) echoed a
``reasoning.context`` or ``reasoning.effort`` other than the one requested. Echo exclusions are
counted per cell, and a cell above 5% is flagged (§13's stop-and-tell rule). Content failures
(unparsed, invalid or incomplete answers) score 0 and stay in (§2.6, §13). Primary analyses use
repeat 0 only (§2.9), templates 0 to T - 1 (T = ``registered.LUNA_T`` = 200, R6 change 6).

**Refusal** (exit 2). Without ``--allow-incomplete`` the script refuses while any required
repeat-0 episode of templates 0 to T - 1 has no record or is pending, in any of the 6 run kinds
(with ``--sweep-closed``, only the two cases above), or a window-cell run's transcript is
missing (the accounting check cannot be made). With ``--allow-incomplete`` it reports what
exists, labelled **PROVISIONAL**, with no confirmatory claim. Also PROVISIONAL (not the
registered analysis): ``--boot`` other than 10,000, ``--no-bayes``, and no ``--run`` list. It
refuses in any case on an undeclared duplicate, on a record that does not fit its run or cannot
be read (a truncated JSON line, a ``repeat_index`` that is not an integer), on a ``--run`` that
is not found, and on the §2.8 bug stop.

**The §2.8 accounting check (the bug stop).** Two conditions, on every window-cell (W-0, W-n-0)
record that reached its need step, in every run read (both repeats, counted or dropped):

1. at far distance, ``S_verbatim`` = 1 is impossible (§2.7);
2. ``S_verbatim`` (the runner's ``need_payload.S``) equals the survival recomputed by replaying
   the drop-oldest rule on the project-token counts of the turns actually sent: from the
   transcript, each step request's observation (its last user message) and each response's
   visible reply are counted with the run's tokenizer, the system prompt is the request's
   ``instructions`` without the notes sentence (counted only when the run's config counts it,
   D5), and ``persistgym.survival.window_keep_start`` is applied at every request up to the
   need step's first one, keeping the largest start (dropped turns never come back,
   harnesses/DESIGN.md §4.2). The evidence survives iff the turn that first showed each evidence
   step is kept. Lookup turns shift the turns, so the replay follows the transcript's turns, not
   the steps.

If either fails for any episode, the script stops (exit 2), names the episodes and reports no
result (§2.8: "analysis stops until it is found"). A replayed window start that differs from the
runner's ``need_info.keep_start``, or a need payload whose number of user messages differs from
the replay's, while ``S`` agrees, is reported as a warning: §2.8's condition is on ``S``. The
runner records ``need_payload`` before it sends the need step's first call and the transcript
only after a call returns, so an episode stopped by that very call (``API_ERROR``,
``COST_CAP``, ``RUN_STOPPED``, ``ERROR:*``) has no recorded need request: it is skipped, with a
warning (it is re-run or continued anyway). The same gap in an episode with a final ending is
a bug. A window-cell record with no ``need_payload.S``: ending ``DONE`` (the episode finished,
so it played its need step) it is a bug stop; with another final ending (an echo mismatch or
``MAX_TURNS`` before the need step) it never reached its need step's request, and is counted in
a warning; with an ending that is not final, it is skipped as above.

**Confirmatory** (§3 H1, §3 H3, §9.1, §9.4; R6 change 9). p(cell) is the mean ``need_correct``
over the cell's primary episodes.

* **H1.** Penalty_NR = p(F-0, NR) - p(W-0, NR) and Penalty_R = p(F-0, R) - p(W-0, R) on the
  observed-far task cells; Δ_H1 = Penalty_NR - Penalty_R. Test: H0 is Δ_H1 ≤ 0; p1 = the share
  of bootstrap resamples with Δ_H1* ≤ 0. Model check (§9.4: "the confirmatory GLM estimate has
  the same sign"): the §9.1 confirmatory GLM's logit-scale Δ_H1 is positive (> 1e-8,
  power_sim's threshold). When an H1 cell has no outcome variation the logit-scale Δ_H1 is not
  finite; how the check reads it then is `H1_SEPARATION_RULE`, ruled ``"firth"`` by the
  researcher on 2026-10-10 (ruled item 1 below). **Kill**
  (as written): Δ_H1 < 10pp (point estimate) and the upper bound of its 90% CI < 15pp.
  **Predictions** (point estimates): the manipulation check Penalty_NR ≥ 25pp; |Penalty_R| ≤
  5pp; the lookups ratio ≥ 1.30 (or, if F-0 looked nothing up, the 90% CI of the difference
  above 0); R_need ≥ 1.30.
* **H3.** Δ_H3 = p(single-turn) - p(F-0), both pooled over observed- and derived-nonrec-far.
  Test: H0 is Δ_H3 ≥ 5pp; p3 = the share of resamples with Δ_H3* ≥ 5pp. The prediction holds
  iff the upper bound of the 90% CI is ≤ 5pp (one-sided non-inferiority at 0.05), reported
  either way. Model check, as §9.4 registers it: "a binomial GLM with template fixed effects
  and an arm indicator (single-turn vs multi-turn) on the H3 cells gives a probability-scale
  Δ_H3 below 5pp" (`h3_glm_literal`; statsmodels, the average marginal effect of the arm,
  reading 15). power_sim's model, which adds a derived-cell term (``ps.h3_glm_ame``), is a
  sensitivity analysis only.
* **Holm** over the family of 2 (H1, H3) at familywise 0.05, the researcher's decision of
  2026-10-06 (R6 change 9); the family of 4, with H2's two tests counted as not rejected
  (p = 1), as a sensitivity analysis. A hypothesis is **supported** only if its Holm test (family
  of 2) rejects and its model check agrees (§9.4, D26).
* **Verdicts.** H1: supported, the kill rule fires (both can hold), or inconclusive
  (``results/decisions.md``, 2026-10-10: "an H1 or H3 result that is neither supported nor
  killed is called inconclusive"). H3 has no kill rule: supported; "not supported: the whole 90%
  CI of Δ_H3 lies above 5pp, against the prediction" (reading 16); or inconclusive. When the
  Holm test rejects but the model check does not agree, the verdict says so.
* **Intervals:** template-cluster bootstrap, 10,000 resamples of templates 0 to T - 1 with
  replacement (``rng.integers``), each contrast recomputed from all of the resampled templates'
  episodes in its cells (ratios of sums), percentile 90% and 95% intervals (``numpy.quantile``,
  linear). Every contrast uses the same resamples. Point estimates are exact fractions, so a
  reading on a threshold is judged exactly; a bound or a resample within 1e-9 of a threshold
  counts as equal to it.
* **GLMs** (§9.1, D25). The confirmatory GLM and H3's model check are fitted by ``statsmodels``
  itself (§9.1: "``statsmodels`` binomial GLM with template dummies and a covariance clustered
  by template"; `sm_fe_logit`): IRLS with its default stopping rule, template dummies, and the
  cluster-robust covariance without statsmodels' correction, times G/(G - 1) (§9.1: that factor
  only). Templates with no outcome variation are dropped from the GLM only (counted). Under
  quasi-separation statsmodels returns large finite coefficients (its stopping point) and no
  finite SE; the cell pattern behind it is reported (`logit_status`). ``analysis.power_sim``'s
  Newton emulation of the same fit (`ps._fe_logit_mle`) is reported next to each estimate as a
  cross-check, and a sign difference is flagged. The §9.1 GLM is fitted on F-0 and W-0, base
  episodes, all 8 task cells, with the saturated harness x recoverable x derived x distance
  terms coded so that the reference is (F-0, not recoverable, observed, far): its W-0 x R
  coefficient is the logit-scale Δ_H1. Both scales are reported (§9.3), with Wald intervals on
  the logit scale, and a sign disagreement is flagged.

**Secondary, as registered.**

* §3 H1: the manipulation check with its CIs; the recoverable-success prediction; the lookups
  ratio (mean ``n_lookups``, W-0 over F-0, observed-far-R) with its zero-lookup rule; R_need =
  [N(W-0, far)/N(F-0, far)] / [N(W-0, near)/N(F-0, near)], N the mean ``need_phase.tokens`` over
  observed-R episodes; R_tok, the same on provider-reported total tokens per episode
  (``usage.input_tokens + usage.output_tokens``), and the literal ratio T(W-0, far)/T(F-0, far);
  W-n-0 alongside (its penalties against F-0, the notes-rescue condition).
* §2.8 accounting by harness cell x task cell (base, repeat 0): S_planned, S_verbatim,
  S_carried, S; expected near losses and S_planned ≠ S_verbatim mismatches (reported, not
  excluded, §13); P(carried), P(used | carried), P(rescued | not carried) split by whether a
  lookup was taken, and the residual at S = 1 (§2.8, §9.6); Σ-n-0 split by
  ``compacted_between`` (D12; exploratory, §9.10).
* §9.5 cost outcomes: per task cell, a log-link Poisson GLM (quasi-Poisson variance) with
  template fixed effects and template-clustered covariance (G/(G - 1)), harness indicators
  against F-0 (the comparison is reading 11, not registered); the ratio is exp(β), with 95% and
  90% Wald intervals. Outcomes: provider-reported total tokens, reasoning tokens, lookups, and
  dollars at list and as the billed estimate. Templates whose outcome is 0 in every row are
  dropped from the fit (their fixed effect is -inf) and counted. A harness cell with no events
  at all (for example no lookups) has ratio 0 and no interval; with no events in F-0 no ratio
  is finite and none is reported. Σ-n-0's ratios are exploratory.
* Every cell's success rate (descriptive; Σ-n-0 exploratory), exclusions and content failures
  per cell.
* If more than one returned model string appears, Δ_H1 and Δ_H3 per string, with their
  bootstrap intervals on the same resamples (§6); records whose responses came from more than
  one string form a group of their own (reading 12).

**Repeats** (§2.9). Repeat 1 only estimates within-template noise: the agreement of the
outcome between the two plays of each episode, per run kind, descriptive, never in a primary
result.

**Bayesian GLMM** (§9.1's sensitivity model: "a Bayesian logistic GLMM with template random
intercepts (e.g. ``bambi``)"; added with ``uv add bambi`` as §9.1 says). `bayesian_glmm` fits
``success ~ W*R*D*N + (1|template)`` with family ``bernoulli`` on the §9.1 GLM's rows (F-0 and
W-0, base, 8 task cells, repeat 0), every template kept (random intercepts need no dropping), with
bambi's default priors, 4 chains of 1,000 draws after 1,000 tuning steps, one core, and seed
SEED + 11 (reading 21). It reports the posterior of the W-0 x R coefficient (the logit-scale
Δ_H1): median, 90% and 95% equal-tailed intervals, P(> 0), R-hat and bulk ESS, and whether its
median's sign matches the confirmatory GLM's. R-hat above 1.01 on any parameter is flagged as
not converged. It enters no decision.

**As implemented.**

*How this differs from analysis/power_sim.py's luna part* (which sized T and gave the achieved
power quoted with the results).

* H1's model check. power_sim stood in for the §9.1 GLM with a smaller model, for the sign only:
  template fixed effects and W, R and W x R on H1's 4 cells (``ps.h1_glm``), read through the
  stopping rule under separation. Here the sign comes from the §9.1 confirmatory GLM itself, as
  §9.4 says, read by `H1_SEPARATION_RULE` when it is not finite. The stand-in is computed too
  (equal to ``ps.h1_glm`` on complete data, tested) and reported; a sign disagreement between
  the two is flagged.
* H3's model check. power_sim used template fixed effects, a derived-cell term and the arm
  (``ps.h3_glm_ame``). Here the decision uses §9.4's model as registered: template fixed
  effects and the arm. power_sim's model is reported as a sensitivity analysis (equal to
  ``ps.h3_glm_ame`` on complete data with two or more templates with outcome variation, tested;
  with one, ``ps.h3_glm_ame`` gives no estimate and this one fits the model, item B below), and
  a disagreement about the 5pp bound between the two is flagged.
* So the achieved power quoted (P(supported) at T = 200: 0.647 and 0.781 in the primary
  scenario, 0.438 and 0.443 in the pessimistic one) was computed with power_sim's model checks
  and with F-0 at 0.95 (0.85) in the observed-far cells. If F-0 sits at its ceiling, H1's model
  check meets separation. Under the literal rule (not in force) P(supported) would be lower
  than quoted (review of 2026-10-10: with F-0 observed-far at 0.995, it failed in 6 of 40 and
  in 28 of 100 simulated sweeps with a true Δ_H1 near 78pp). The rule in force (``"firth"``,
  ruled 2026-10-10) reads a finite penalized estimate instead; power_sim did not simulate it,
  so its effect on P(supported) is not known. The summary says so.
* The bootstrap. power_sim drew counts of identical per-template integer rows, assuming one
  outcome per template and cell; here templates are drawn by index and each contrast is a ratio
  of sums, which also handles exclusions. With complete data both give the same contrast for
  the same resampled templates (tested); the random draws differ (seed SEED + 10 here).
* power_sim fitted a model check only when its test rejected at 0.05 (for speed); here they are
  always fitted. power_sim compared integer sums; here floats are compared with the 1e-9
  tolerance above, on the null side.

*Readings of PREREG made here* (none changes a hypothesis, prediction or threshold).

1. The key of §7.8 is applied per harness cell (above).
2. ``AGENT_ERROR`` (a Σ-cell summary that failed every attempt) is the episode's own ending, so
   it is final: it scores 0 unless its need step was scored, and is counted. §7.8 lists it
   neither way. An ending this script does not know is treated as not final and listed.
3. "Required" for completeness: the 6 run kinds of R6 change 1 at repeat 0. Repeat-1 runs are
   not required; if one is missing, the agreement is reported for what exists.
4. ``S_verbatim`` is the runner's ``need_payload.S``. The runner's string search also covers the
   need observation, which §2.8 excludes; in a base episode the need observation holds no
   evidence binding (§2.3, §2.4), so the two agree. The accounting reads base episodes only.
5. ``S_carried``: in W-n-0 the retained replies of the need payload
   (``need_payload.assistant_carried.carried``); in Σ-n-0 those or the summary bridge
   (``need_bridge_carried.carried``). F-0 and W-0 have no notes or summary, so S_carried is
   undefined there and S = S_verbatim; their rescue rate is P(success | S_verbatim = 0), split
   by lookup.
6. "A lookup was taken" is ``n_lookups`` ≥ 1 (lookups served; over-cap ones come only after 3
   served ones).
7. (Moved to ruled item 2 below.)
8. The logit scale of §9.3 comes from the GLMs (Δ_H1: the §9.1 GLM's W-0 x R coefficient, and
   the penalties from its W-0 and W-0 x R coefficients; Δ_H3: the arm coefficient of §9.4's H3
   model), with cluster-robust Wald intervals. Logits of cell means are not used: a cell mean
   of 0 or 1 has none.
9. One-sided bootstrap p-values count ties on the null side (D26), with the 1e-9 tolerance.
   A resample in which a contrast is undefined (a cell with no episode, or a zero denominator)
   is left out of that contrast's intervals and p-value, and counted.
10. R_need's N(h, d) uses the episodes whose need phase is complete (``need_phase.complete``)
    and has a token count; the others are counted and left out (a complete need phase without
    ``tokens`` is also warned about). T(h, d) uses every primary episode of the cell.
11. Cost outcomes (§9.5 names no comparison): within each task cell, each harness cell against
    F-0. Labelled as this reading in the summary.
12. The model-string split (§6) groups records by the set of strings their responses returned:
    one group per single string, and one for the records whose responses came from more than
    one string (counted, not dropped).
13. (Replaced by ruled item 1 below: ``"firth"``, the researcher's ruling of 2026-10-10.)
14. The bootstrap resamples templates 0 to T - 1 (all of them), so a template whose episodes
    were all excluded still counts as a template with no episodes in the cell.
15. H3's probability-scale Δ_H3 from the GLM is the average marginal effect of the arm over
    every (template, task cell) pair of the H3 cells, as power_sim computes it: a template with
    no outcome variation adds 0 (its fixed effect is infinite, so both arms' fitted success is
    0 or 1; its observed difference is 0 too). That keeps the model's Δ_H3 on the scale of the
    probability-scale Δ_H3, whose 5pp bound is an average over all templates. The average over
    the informative templates only is larger in size and is reported next to it.
16. H3's verdict when it is not supported: "inconclusive", the wording of the decision of
    2026-10-10, except when the lower bound of the 90% CI of Δ_H3 is above 5pp, where the data
    go against the prediction and the verdict says "not supported" with that reading. The
    decision's sentence was written about low power; it does not fit a result that excludes
    the bound.
17. ``--sweep-closed``, above: §7.8's exclusion of a key with no final record, applied only
    when the researcher has closed the sweep; a key whose last record is a single
    ``API_ERROR`` still needs its §13 re-run.
18. FINAL needs the ``--run`` input list (DESIGN §7.8).
19. The §2.8 check's handling of a window-cell record without ``need_payload.S`` (above).
20. A ``repeat_index`` that is present but not an integer (``null``, a string) is refused, not
    read as 0: only an absent field means repeat 0 (DESIGN §7.8).
21. The Bayesian sensitivity model's settings (above) are not registered beyond §9.1's
    sentence: its terms are the §9.1 GLM's, its priors bambi's defaults, its seed SEED + 11
    (SEED + 10 is the bootstrap's, SEED + 20 the failure labels', SEED + 30 H4's).

*Ruled by the researcher* (PREREG does not settle items 1 and 2; the researcher's ruling of
2026-10-10 is recorded in ``results/decisions.md``, made before any result of the sweep was read;
items 3 and 4 are readings, listed above).

1. **H1's model check when the logit-scale Δ_H1 is not finite** (review finding B2). When an
   H1 cell (F-0 or W-0 at observed-far, NR or R) has no outcome variation among the GLM's
   templates, the W-0 x R coefficient has no finite maximum-likelihood value: statsmodels
   returns its stopping point. The limit's sign follows from which cells are all 0 or all 1:
   ``logit Δ_H1 = logit p(F-0, NR) - logit p(W-0, NR) - logit p(F-0, R) + logit p(W-0, R)``, so
   for example F-0 observed-rec-far all 1 gives -∞, W-0 observed-nonrec-far all 0 gives +∞, and
   cells pushing both ways give ∞ - ∞, an undefined sign. **Ruling (2026-10-10):**
   `H1_SEPARATION_RULE` is ``"firth"``: when the logit-scale Δ_H1 is not finite, the model check
   reads the W-0 x R coefficient of a Firth-penalized fit of the same model on the same rows
   (`firth_fe_logit`), the standard remedy for separation; when it is finite, the ordinary fit
   decides as before. Not in force, kept for the sensitivity lines only: ``"literal"`` (the
   limit's sign: +∞ agrees, -∞ and an undefined sign do not) and ``"probability-scale"`` (the
   model check not applicable; the probability-scale sign is read). The summary names the rule
   in force and, when the logit-scale Δ_H1 is not finite, reports as sensitivity lines what
   each other rule would have said: its model check and H1's verdict (`h1_rule_sensitivity`;
   they enter no decision).
2. **The harness levels of the §9.1 GLM** (finding S4; was reading 7; as proposed, confirmed by
   the researcher's merge of the 2026-10-10 ruling). PREREG says "harness x
   recoverable x derived x distance terms" without naming the levels. The confirmatory fit uses
   H1's harness cells, F-0 and W-0, on all 8 task cells: Σ-n-0 enters no confirmatory test
   (D12), and W-n-0 is "reported alongside" H1, not part of its comparison (§3 H1). The fit with
   W-n-0 as a third level is reported as a sensitivity analysis, with a flag if its W-0 x R
   coefficient's sign differs.
3. **A closed sweep** (finding S2): reading 17 above.
4. **H3's wording** (finding S5): reading 16 above.

*Changed after the FINAL output was read* (the researcher's decisions of 2026-10-10,
``results/decisions.md``; the output before each change is kept and reported with the one
after it):

A. **The Firth fit's step cap**, 100 to 1,000 (`firth_fe_logit`). On luna's sweep the fit's
   linearly converging steps needed 103, so H1's model check read "did not converge".
B. **One template with outcome variation is enough to fit** a fixed-effects logit
   (`fe_logit_fit`, `h3_glm_powersim`): its point estimates or, under quasi-separation,
   statsmodels' stopping point, as with two or more. The cluster-robust Wald quantities still
   need two, and so do the Firth fit (`glm_91_firth`) and the H1 stand-in (`h1_standin`). On
   luna's sweep H3's cells had one such template, so H3's model check returned no estimate,
   which reads as "does not agree". With one template the model is saturated in it, so its
   average marginal effect is the observed Δ_H3 by construction (the summary says so).
C. **The summary's wording**, with no number changed: the reason a fit gave no estimate, "no
   sign to compare" where a sign is missing, the route power_sim's emulation took (`emulate`),
   and the Bayesian GLMM's divergent transitions.

**A second model: claude-haiku-5-5's replication** (``--model claude-haiku-5-5``; PREREG §17.8,
amendment R8, "Status in the analysis"). Every H1 and H3 quantity above is computed on Haiku's
runs exactly as on luna's: the same code, predictions, thresholds and model checks, with the
rules of 2026-10-10 that R8 pre-specifies for Haiku (the §9.1 GLM's harness levels, Firth with
``max_iter`` 1,000, H3's one-template fit, the Bayesian GLMM's settings), and luna's seeds
(bootstrap SEED + 10, Bayesian SEED + 11, so at T = 200 the template resamples are luna's).
What differs is set by the model's `Profile` (`profile`). luna's profile is the analysis above,
unchanged: on luna's sweep it reproduces the cited output
(``results/persistgym_h1h3/20261010T232227Z/``) number for number and label for label.

* **Runs.** Folders of ``<results root>/persistgym_haiku/`` whose ``meta.json`` is a
  claude-haiku-5-5 run (`registered.model_family`) on the default generator config
  (``registered.HAIKU_GENERATOR_HASH``, luna's), read on main templates 0 to T - 1, T =
  ``registered.HAIKU_T`` (200 unless R8's size record lowers it), with the transcripts under
  ``<raw root>/persistgym_haiku/``. ``--experiment`` reads another experiment's folder (either
  model), and the output is then PROVISIONAL.
* **Run kinds.** F-0 and W-0 on base episodes, F-0 on the restated-at-need control and the
  single-turn control, and W-n-0 if it runs: the harness cells are ``registered.HAIKU_CELLS``,
  read at call time, which R8's size record sets without W-n-0 if W-n-0 does not run. A W-n-0
  run is then refused, and W-n-0 is reported as "pre-registered, not run (budget)", with no
  alongside reading, §9.1 sensitivity fit, cost ratio or accounting row. No Σ-n-0 (R8).
* **No echo** (R8, What it changes 5). The Messages API echoes neither effort nor a reasoning
  context, so no Haiku record is excluded for an echo: the echo endings and fields are not read.
  A record the runner marked ``excluded`` (it never marks one on the Messages wire) would still
  be excluded, as "excluded by the runner". The substitutes, the request-side check and the
  payload snapshot tests, act before a request is sent; a run that the request-side check
  stopped (``ERROR:RequestCheckFailed``) is named in the Checks.
* **Usage.** The runner records Messages usage in the Responses meanings
  (`harnesses.pricing.messages_usage_numbers`): ``input_tokens`` already includes the cache
  reads and writes, so total tokens are ``input_tokens + output_tokens`` as on luna, and nothing
  is added twice. Reasoning tokens a response did not report are null in the record, so that
  episode's are missing (never 0); a §9.5 outcome missing in every episode of a task cell is
  reported as unavailable.
* **§2.8's replay on Messages transcripts** (`window_recheck`). The system prompt is the
  request's ``system``, the observation the last of its ``messages`` (text blocks), and a turn's
  reply the response's text blocks as the session kept and W counted them
  (`MessagesWire.kept_reply`: the empty text for a refusal). A turn with no visible reply counts
  0 tokens: the ``(no reply)`` placeholder that went back in its place is not its reply
  (harnesses/wire.py, ``EMPTY_REPLY_PLACEHOLDER``).
* **Refusals and stops** (R8, Exclusions) are content failures that score 0 and stay in, as on
  luna; per cell, the step responses that stopped short are also counted by reason
  (``refusal:<category>``, ``max_output_tokens``).
* **Labels** (R8, Status in the analysis): outside luna's Holm family, H1's test (H0: Δ_H1 ≤ 0)
  and H3's (H0: Δ_H3 ≥ 5pp) are read with their unadjusted one-sided bootstrap p-values at 0.05
  and their model checks (`replication_readings`). Each label says whether the test rejects
  and whether the model check agrees, and carries no confirmatory word. H1's predictions and
  kill reading are computed as on luna; the kill rule reads luna only, so here it neither kills
  nor confirms H1.
* **Power** at the chosen T comes from ``--power-path``, a per-T power table of
  ``analysis.power_sim``'s luna part (its ``luna_power.csv``) simulated with Haiku's
  assumptions (R8): its rows at T, P(the unadjusted test rejects) and P(it rejects and the
  model check agrees). Without one, power is reported as unavailable.
* **Output:** ``<results root>/persistgym_h1h3_haiku/<UTC>/``, the same three files; the
  summary's "What it does not show" is R8's.

**What this does not do.** No failure labels (§9.7; void under R6), no exploratory analysis
(§9.10), no H2 (stopped under R3) and no sol replication (not run under R6). It does not read
``results/decisions.md``: the re-run links, the input list and the closing entry are passed by
hand. It never prints an outcome unless it is run, and it should first be run only after the
researcher's review.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.metadata
import json
import logging
import math
import sys
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from fractions import Fraction
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import linalg, special
from statsmodels.tools import sm_exceptions

from analysis import power_sim as ps
from common import runmeta
from harnesses import registered
from harnesses.cells import CELLS, NOTES_INSTRUCTION
from harnesses.items import item_text, output_text
from harnesses.wire import MESSAGES, MESSAGES_API, RESPONSES_API
from persistgym import tokens
from persistgym.episode import TaskCell
from persistgym.survival import window_keep_start

REPO_ROOT = runmeta.REPO_ROOT
RESULTS = REPO_ROOT / "results"
EXPERIMENT = registered.LUNA_EXPERIMENT                 # "persistgym"
OUT_NAME = "persistgym_h1h3"
MODEL = registered.LUNA_MODEL                           # "gpt-6-luna"
T_REGISTERED = registered.LUNA_T                        # 200, R6 change 6
GENERATOR_HASH = registered.LUNA_GENERATOR_HASH         # the default config
HARNESS_CELLS = registered.LUNA_CELLS                   # F-0, W-0, W-n-0, Σ-n-0
SINGLE_TURN = registered.LUNA_SINGLE_TURN_CELL          # "single-turn"
TASK_CELLS = registered.LUNA_TASK_CELLS
NR_TASK_CELLS = registered.LUNA_SINGLE_TURN_TASK_CELLS
BASE, RESTATED = "base", "restated"
KINDS = (("F-0", BASE), ("W-0", BASE), ("W-n-0", BASE), ("Σ-n-0", BASE), ("F-0", RESTATED),
         (SINGLE_TURN, BASE))
"""The run kinds of R6 change 1: (harness cell, variant)."""
WINDOW_CELLS = tuple(c for c in HARNESS_CELLS if CELLS[c].history == "window")
CARRY_CELLS = tuple(c for c in HARNESS_CELLS
                    if CELLS[c].notes or CELLS[c].history == "summary")
SUMMARY_CELLS = tuple(c for c in HARNESS_CELLS if CELLS[c].history == "summary")
OBS_NR_FAR, OBS_R_FAR = "observed-nonrec-far", "observed-rec-far"
OBS_R = {"near": "observed-rec-near", "far": "observed-rec-far"}
H3_CELLS = ("observed-nonrec-far", "derived-nonrec-far")

ALPHA = 0.05
N_BOOT = 10_000                                          # §9.1
BOOT_SEED_OFFSET = 10                                    # §9.1: SEED + 10
LEVELS = (0.90, 0.95)
TOL = 1e-9
MANIPULATION_MIN = Fraction(1, 4)                        # §3 H1: Penalty_NR >= 25pp
RECOVERABLE_BAND = Fraction(1, 20)                       # §3 H1: |Penalty_R| <= 5pp
KILL_POINT = Fraction(1, 10)                             # §3 H1 kill: < 10pp
KILL_UPPER = 0.15                                        # ... and 90% upper bound < 15pp
RATIO_MIN = Fraction(13, 10)                             # §3 H1: lookups, R_need >= 1.30
H3_MARGIN = Fraction(1, 20)                              # §3 H3: 5pp
GLM_SIGN_EPS = 1e-8                                      # power_sim's "positive" interaction
ECHO_SHARE_MAX = 0.05                                    # §13
H2_TESTS_NOT_RUN = 2                                     # the family-of-4 sensitivity
Z90, Z95 = 1.6448536269514722, 1.959963984540054

CHANGED_AFTER_FINAL = (
    "A: the Firth fit's step cap, 100 to 1,000 (H1's model check had read 'did not converge')",
    ("B: one template with outcome variation is enough to fit a fixed-effects logit (H3's "
     "model check had returned no estimate)"),
    "C: the summary's wording, with no number changed")
H1_SEPARATION_RULES = ("literal", "firth", "probability-scale")
H1_SEPARATION_RULE = "firth"        # the researcher's ruling of 2026-10-10 (decisions.md)
"""How H1's model check reads the §9.1 GLM when the logit-scale Δ_H1 is not finite (ruled item
1 of the module docstring). "firth" is the researcher's ruling of 2026-10-10, recorded in
results/decisions.md before any result of the sweep was read; it replaced "literal", the more
conservative reading that was in force until the ruling. The rule is changed only by a commit
of this line, so the rule in force is in the output's git commit."""
FINITE, PLUS_INF, MINUS_INF, UNDEFINED = "finite", "+inf", "-inf", "undefined"

BAYES_SEED_OFFSET = 11                                   # reading 21
BAYES_SETTINGS = {"chains": 4, "draws": 1000, "tune": 1000}
BAYES_FORMULA = "success ~ W*R*D*N + (1|template)"
RHAT_MAX = 1.01

FINAL_ENDINGS = ("DONE", "MAX_TURNS", "REASONING_CONTEXT_MISMATCH",
                 "REASONING_EFFORT_MISMATCH")
AGENT_ERROR = "AGENT_ERROR"                              # final here (reading 2)
API_ERROR = "API_ERROR"
NOT_FINAL = ("API_ERROR", "COST_CAP", "RUN_STOPPED")     # and "ERROR:*"
ECHO_EXITS = ("REASONING_CONTEXT_MISMATCH", "REASONING_EFFORT_MISMATCH")
POWER_DECISION = RESULTS / "power_sim" / "20261010T030442Z" / "luna_decision.csv"
POWER_READING = "worst Holm step, supported (decision)"
COST_OUTCOMES = {"tokens_total": "total tokens (input + output)",
                 "reasoning_tokens": "reasoning tokens", "n_lookups": "lookups",
                 "cost_list": "USD, list", "cost_billed": "USD, billed estimate"}
OUTPUTS = ("h1h3.json", "summary.md")
FINAL, PROVISIONAL = "FINAL", "PROVISIONAL"

# --- R8 (PREREG §17.8): claude-haiku-5-5's replication ("A second model" above) ---
HAIKU_OUT_NAME = "persistgym_h1h3_haiku"
R8_CELLS = ("F-0", "W-0", "W-n-0")
"""The harness cells R8 registers for Haiku; W-n-0 runs only under its size rule, and
``registered.HAIKU_CELLS`` (read at call time) says whether it does."""
LUNA_CITED_OUTPUT = "results/persistgym_h1h3/20261010T232227Z/"
"""luna's cited H1/H3 output (results/decisions.md, 2026-10-10), which stays primary (R8)."""
REQUEST_CHECK_STOP = "ERROR:RequestCheckFailed"
"""The exit reason of a Messages run that the request-side check stopped (harnesses/DESIGN.md
§13.2): a harness bug; R8 excludes the episode, whose record is never written."""
NOT_RUN_BUDGET = "pre-registered, not run (budget)"
PRE_SPECIFIED = (
    ("the §9.1 GLM's harness levels are F-0 and W-0 on all 8 task cells, with W-n-0 as a "
     "third level in a sensitivity fit if it runs"),
    ("H1's model check reads a Firth-penalized fit when the logit-scale Δ_H1 is not finite, "
     "with max_iter 1,000"),
    "H3's model check is fitted even when only one template has outcome variation",
    ("the Bayesian GLMM uses bambi's default priors, 4 chains × 1,000 draws after 1,000 tuning "
     "steps"),
    "the seeds are luna's: bootstrap SEED + 10 and Bayesian SEED + 11")
"""R8's pre-specified rules (§17.8, Status in the analysis): fixed for luna on 2026-10-10,
after luna's data and before any Haiku data."""
POWER_TABLE_COLUMNS = ("scenario", "templates", "P_h1_unadjusted", "P_h3_unadjusted",
                       "P_h1_glm_veto", "P_h3_glm_veto")
"""The columns of power_sim's per-T luna power table (``luna_power.csv``) that Haiku's power
reading needs (`replication_power`)."""


class Refusal(ValueError):
    """Inputs this analysis cannot be computed from (exit 2)."""


class AccountingBug(Refusal):
    """PREREG §2.8's bug stop: a window-cell episode breaks the accounting conditions."""


# --- profiles: what one model's analysis reads, and how it labels its tests ---------------

@dataclass(frozen=True)
class Profile:
    """One model's analysis (`profile`). luna's is the pre-registered analysis of its sweep;
    Haiku's is R8's replication (PREREG §17.8), computed the same way on Haiku's runs."""
    model: str                       # the registered model (`registered.model_family`)
    name: str                        # in messages: "luna", "Haiku"
    experiment: str                  # the folder read (--experiment, else the registered one)
    registered_experiment: str
    out_name: str                    # the output folder under the results root
    T: int
    generator_hash: str
    cells: tuple[str, ...]           # the harness cells read (not the single-turn control)
    registered_cells: tuple[str, ...]
    task_cells: tuple[str, ...]
    nr_task_cells: tuple[str, ...]
    api: str                         # the wire's API: transcripts and echo
    replication: bool                # R8: outside the Holm family, unadjusted p-values
    power_path: Path | None          # the default power file

    @property
    def kinds(self) -> tuple[tuple[str, str], ...]:
        """The run kinds (harness cell, variant), luna's in the order of `KINDS`."""
        return (*((c, BASE) for c in self.cells), ("F-0", RESTATED), (SINGLE_TURN, BASE))

    @property
    def echo(self) -> bool:
        """Whether the API echoes the reasoning settings (§13's echo exclusion applies)."""
        return self.api == RESPONSES_API

    @property
    def not_run(self) -> tuple[str, ...]:
        """Registered cells that do not run (Haiku's W-n-0 under R8's size rule)."""
        return tuple(c for c in self.registered_cells if c not in self.cells)

    def public(self) -> dict:
        return {"model": self.model, "name": self.name, "experiment": self.experiment,
                "registered_experiment": self.registered_experiment,
                "out_name": self.out_name, "T": self.T, "api": self.api,
                "cells": list(self.cells), "cells_not_run": list(self.not_run),
                "replication": self.replication, "prereg": R8_PREREG}


R8_PREREG = ("PREREG.md §17.8 (amendment R8): §3 H1, §3 H3, §2.8, §2.9, §9.1-§9.5, §13 as on "
             "luna; outside the Holm family")


def profile(model: str | None = None, experiment: str | None = None) -> Profile:
    """The analysis of `model` (default luna's), reading `experiment` (default the model's
    registered one). luna's is built from this module's constants and Haiku's from
    `registered.HAIKU_*`, both read at call time (R8's size record sets ``HAIKU_T`` and
    ``HAIKU_CELLS``)."""
    model = model or MODEL
    if model == MODEL:
        prof = Profile(model=MODEL, name="luna", experiment=EXPERIMENT,
                       registered_experiment=EXPERIMENT, out_name=OUT_NAME, T=T_REGISTERED,
                       generator_hash=GENERATOR_HASH, cells=tuple(HARNESS_CELLS),
                       registered_cells=tuple(HARNESS_CELLS), task_cells=tuple(TASK_CELLS),
                       nr_task_cells=tuple(NR_TASK_CELLS), api=RESPONSES_API,
                       replication=False, power_path=POWER_DECISION)
    elif model == registered.HAIKU_MODEL:
        cells = tuple(registered.HAIKU_CELLS)
        if not {"F-0", "W-0"} <= set(cells) or not set(cells) <= set(R8_CELLS):
            raise Refusal(f"registered.HAIKU_CELLS is {cells!r}: R8 registers F-0 and W-0, and "
                          "W-n-0 only under its size rule")
        prof = Profile(model=registered.HAIKU_MODEL, name="Haiku",
                       experiment=registered.HAIKU_EXPERIMENT,
                       registered_experiment=registered.HAIKU_EXPERIMENT,
                       out_name=HAIKU_OUT_NAME, T=registered.HAIKU_T,
                       generator_hash=registered.HAIKU_GENERATOR_HASH, cells=cells,
                       registered_cells=R8_CELLS,
                       task_cells=tuple(registered.HAIKU_TASK_CELLS),
                       nr_task_cells=tuple(registered.HAIKU_SINGLE_TURN_TASK_CELLS),
                       api=MESSAGES_API, replication=True, power_path=None)
    else:
        raise Refusal(f"--model {model!r}: this analysis covers {MODEL} (the pre-registered "
                      f"sweep) and {registered.HAIKU_MODEL} (R8's replication) only")
    return replace(prof, experiment=experiment) if experiment else prof


# --- runs ----------------------------------------------------------------------------------

@dataclass
class Run:
    """One luna run folder of experiment persistgym: its meta.json fields and its records."""
    run_id: str
    folder: Path
    cell: str
    variants: tuple[str, ...]
    repeat_index: int
    started: datetime
    exit_reason: str | None
    model_returned: list
    records: list[dict]
    window: dict


def _window_settings(meta: dict) -> dict:
    """W, whether the system prompt counts, the notes separator and the tokenizer of a run,
    from its meta.json config (the harness's value, else the episode generator's)."""
    cfg = meta.get("config") or {}
    h, g = cfg.get("harness") or {}, cfg.get("generator_config") or {}
    count = h.get("window_counts_system_prompt")
    return {"W": h.get("W_tokens") if h.get("W_tokens") is not None else g.get("W_tokens"),
            "count_system": bool(g.get("window_counts_system_prompt") if count is None
                                 else count),
            "notes_separator": h.get("notes_separator", "\n"),
            "tokenizer": h.get("tokenizer") or g.get("tokenizer") or "o200k_base"}


def _not_ours(meta: dict, prof: Profile | None = None) -> str | None:
    """Why a run folder is not one of the model's sweep runs (luna's by default) on the
    default config, or None."""
    prof = prof or profile()
    if meta.get("experiment") != prof.experiment:
        return f"experiment {meta.get('experiment')!r}"
    model = str(meta.get("model_requested"))
    if registered.model_family(model) != prof.model:
        return f"model {model!r}, not {prof.model}"
    hashes = (meta.get("config") or {}).get("generator_config_hashes")
    if hashes != [prof.generator_hash]:
        return (f"generator config {hashes!r}, not the default config "
                f"{prof.generator_hash[:12]}")
    return None


def template_index(template_id: str) -> int:
    split, _, num = str(template_id).partition("-")
    if split != "main" or not num.isdigit():
        raise Refusal(f"template {template_id!r} is not on the main split")
    return int(num)


def _check_record(run_id: str, cell: str, repeat: int, rec: dict,
                  prof: Profile | None = None) -> None:
    prof = prof or profile()
    where = f"{run_id}: record {rec.get('episode_id')!r}"
    if rec.get("harness_cell") != cell:
        raise Refusal(f"{where} has harness cell {rec.get('harness_cell')!r}, its run {cell!r}")
    rep = rec.get("repeat_index", 0)
    if not isinstance(rep, int) or isinstance(rep, bool):
        raise Refusal(f"{where} has repeat_index {rep!r}, not an integer (reading 20: only an "
                      "absent field means repeat 0)")
    if rep != repeat:
        raise Refusal(f"{where} has repeat_index {rep}, its run {repeat}")
    if rec.get("generator_config_hash") not in (None, prof.generator_hash):
        raise Refusal(f"{where} played generator config {rec.get('generator_config_hash')!r}")
    variant = rec.get("variant")
    if variant not in (BASE, RESTATED) or (variant == RESTATED and cell != "F-0"):
        raise Refusal(f"{where} has variant {variant!r} in cell {cell}")
    allowed = prof.nr_task_cells if cell == SINGLE_TURN else prof.task_cells
    if rec.get("task_cell") not in allowed:
        raise Refusal(f"{where} has task cell {rec.get('task_cell')!r}")
    template_index(rec.get("template_id"))


def _read_json(path: Path, what: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Refusal(f"{what}: {path.name} is not valid JSON ({e})") from None


def _read_jsonl(path: Path, run_id: str) -> list[dict]:
    """The records of an episodes.jsonl; a line that is not JSON (a truncated write) refuses."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise Refusal(f"{run_id}: episodes.jsonl line {i} is not valid JSON ({e}); a "
                              "truncated write? Resolve it by hand") from None
    return out


def discover(root: Path, declared: list[str] | None = None,
             prof: Profile | None = None) -> tuple[list[Run], list[dict]]:
    """The model's sweep runs (luna's by default) under root/<its experiment>/ (only those in
    `declared`, the --run input list, when it is given), and the folders skipped with the
    reason."""
    prof = prof or profile()
    base = root / prof.experiment
    if not base.is_dir():
        raise Refusal(f"no {prof.experiment}/ folder under {root}")
    wanted = None if declared is None else set(declared)
    if declared is not None and len(wanted) != len(declared):
        raise Refusal("--run names a run twice")
    runs, skipped = [], []
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        meta_path = folder / "meta.json"
        if not meta_path.is_file():
            skipped.append({"folder": folder.name, "reason": "no meta.json"})
            continue
        meta = _read_json(meta_path, folder.name)
        why = _not_ours(meta, prof)
        if why:
            skipped.append({"folder": folder.name, "reason": why})
            continue
        run_id = str(meta.get("run_id") or folder.name)
        if wanted is not None and run_id not in wanted:
            skipped.append({"folder": folder.name,
                            "reason": f"a {prof.model} sweep run not in the input list (--run)"})
            continue
        ep_path = folder / "episodes.jsonl"
        if not ep_path.is_file():
            raise Refusal(f"{run_id}: a {prof.model} run without episodes.jsonl")
        cell = meta.get("cell_or_config")
        if cell not in (*prof.cells, SINGLE_TURN):
            raise Refusal(f"{run_id}: cell {cell!r} is not one of {prof.name}'s sweep cells"
                          + (f" ({', '.join(prof.cells)}: registered.HAIKU_CELLS, which R8's "
                             "size record sets)" if prof.replication else ""))
        repeat = int(meta.get("repeat_index") or 0)
        records = _read_jsonl(ep_path, run_id)
        for rec in records:
            _check_record(run_id, cell, repeat, rec, prof)
        try:
            started = datetime.fromisoformat(str(meta["started_utc"]))
        except (KeyError, ValueError):
            raise Refusal(f"{run_id}: meta.json has no readable started_utc") from None
        runs.append(Run(run_id=run_id, folder=folder, cell=cell,
                        variants=tuple(sorted({r["variant"] for r in records})),
                        repeat_index=repeat, started=started,
                        exit_reason=meta.get("exit_reason"),
                        model_returned=list(meta.get("model_returned") or []),
                        records=records, window=_window_settings(meta)))
    if wanted is not None:
        missing = sorted(wanted - {r.run_id for r in runs})
        if missing:
            raise Refusal(f"--run names run(s) that are not {prof.model} sweep runs on the "
                          f"default config under {base}: {', '.join(missing)}")
    return runs, skipped


def read_seed(root: Path) -> tuple[int, Path]:
    """SEED (D15) from the one draw/*/draw.json under root."""
    found = sorted((root / "draw").glob("*/draw.json"))
    if len(found) != 1:
        raise Refusal(f"expected exactly one draw/*/draw.json under {root}, found {len(found)}")
    draw = json.loads(found[0].read_text(encoding="utf-8"))
    return int(draw["seed"]["seed"]), found[0]


# --- keys, re-runs and exclusions (DESIGN §7.8, §13) ---------------------------------------

def is_final(ending: str | None) -> bool:
    return ending in FINAL_ENDINGS or ending == AGENT_ERROR


def _known(ending: str | None) -> bool:
    return (is_final(ending) or ending in NOT_FINAL
            or (isinstance(ending, str) and ending.startswith("ERROR:")))


def echo_exclusion(rec: dict, echo: bool = True) -> str | None:
    """Why a counted record is excluded for its echo (§13, R2 change 3), or None. With `echo`
    False (the Messages API echoes nothing: R8) no echo is read, only the runner's mark."""
    if rec.get("excluded"):
        return rec.get("exclusion_reason") or "excluded by the runner"
    if not echo:
        return None
    if rec.get("exit_reason") in ECHO_EXITS:
        return str(rec["exit_reason"])
    echo = rec.get("echo") or {}
    for kind in ("context", "effort"):
        want, seen = echo.get(f"{kind}_requested"), echo.get(f"{kind}_echoed") or {}
        other = sorted(k for k in seen if k != str(want))
        if want is not None and other:
            return (f"reasoning.{kind} echoed {other} (requested {want!r}), not marked "
                    "excluded by the runner")
    return None


@dataclass
class Resolved:
    """One key's outcome under §7.8's rule."""
    key: tuple[str, str, int]          # (harness cell, episode_id, repeat_index)
    status: str                        # counted, excluded or pending
    record: dict | None
    run_id: str | None
    reason: str | None
    dropped: list[dict] = field(default_factory=list)
    n_records: int = 0
    n_api_errors: int = 0
    last_ending: str | None = None     # of the key's last record
    closed: bool = False               # excluded with no final record: the sweep is closed
    awaiting_rerun: bool = False       # its last record is a single API_ERROR (§13)


def parse_links(pairs: list[str] | None) -> dict[str, str]:
    """``--rerun RUN=ORIGINAL`` declarations as {run: original}."""
    out = {}
    for p in pairs or []:
        run, sep, orig = p.partition("=")
        if not sep or not run or not orig:
            raise Refusal(f"--rerun takes RUN=ORIGINAL, got {p!r}")
        if run in out:
            raise Refusal(f"--rerun declares {run} twice")
        out[run] = orig
    return out


def resolve(runs: list[Run], links: dict[str, str], sweep_closed: bool = False,
            echo: bool = True) -> tuple[dict, list[str]]:
    """Every key's counted record, exclusion or pending state; and warnings. With
    `sweep_closed`, a key with no final record is excluded (§7.8), unless its last record is a
    single API_ERROR, whose §13 re-run is still owed (reading 17). With `echo` False (Haiku,
    R8) no record is excluded for an echo (`echo_exclusion`)."""
    ids = {r.run_id: r for r in runs}
    for run, orig in links.items():
        if run not in ids or orig not in ids:
            raise Refusal(f"--rerun {run}={orig}: both must be runs read here")
        if ids[orig].started >= ids[run].started or ids[orig].cell != ids[run].cell:
            raise Refusal(f"--rerun {run}={orig}: the original must be an earlier run of the "
                          "same cell")
    order = sorted(runs, key=lambda r: (r.started, r.run_id))
    by_key: dict[tuple, list[tuple[str, dict]]] = defaultdict(list)
    unknown: Counter = Counter()
    for run in order:
        seen = set()
        for rec in run.records:
            key = (run.cell, rec["episode_id"], int(rec.get("repeat_index", 0)))
            if key in seen:
                raise Refusal(f"{run.run_id}: episode {key[1]!r} (repeat {key[2]}) appears "
                              "twice in one run")
            seen.add(key)
            by_key[key].append((run.run_id, rec))
            if not _known(rec.get("exit_reason")):
                unknown[str(rec.get("exit_reason"))] += 1
    warnings_ = [f"unknown ending {e!r} on {n} record(s): treated as not final"
                 for e, n in sorted(unknown.items())]
    out = {}
    for key, entries in by_key.items():
        before = [entries[0][0]]
        for run_id, _ in entries[1:]:
            if links.get(run_id) not in before:
                raise Refusal(
                    f"{key[0]} {key[1]!r} (repeat {key[2]}) is in {before[-1]} and again in "
                    f"{run_id}, which is not declared as a re-run or continuation of a run "
                    "that holds it (--rerun RUN=ORIGINAL, as listed in results/decisions.md; "
                    "harnesses/DESIGN.md §7.8). Resolve it by hand.")
            before.append(run_id)
        api = 0
        first = None
        for i, (_, rec) in enumerate(entries):
            ending = rec.get("exit_reason")
            if is_final(ending):
                first = i
                break
            api += ending == API_ERROR
        last_run, last = entries[-1]
        r = Resolved(key=key, status="pending", record=None, run_id=None, reason=None,
                     n_records=len(entries), n_api_errors=api,
                     last_ending=last.get("exit_reason"))
        if first is not None and api < 2:
            run_id, rec = entries[first]
            r.record, r.run_id = rec, run_id
            r.dropped = [{"run_id": x, "exit_reason": y.get("exit_reason")}
                         for x, y in entries[first + 1:]]
            why = echo_exclusion(rec, echo)
            r.status, r.reason = (("excluded", f"{'echo' if echo else 'runner'}: {why}") if why
                                  else ("counted", None))
        elif api >= 2:
            r.status = "excluded"
            r.reason = "two transport failures (API_ERROR) before a final record (§13)"
            r.dropped = [{"run_id": x, "exit_reason": y.get("exit_reason")}
                         for x, y in entries[(first if first is not None else len(entries)):]]
        else:
            r.awaiting_rerun = r.last_ending == API_ERROR
            if r.awaiting_rerun:
                r.reason = (f"a transport failure (API_ERROR in {last_run}) not yet re-run: "
                            "§13 re-runs it once")
            elif sweep_closed:
                r.status, r.closed = "excluded", True
                r.reason = (f"no final record (last ending {r.last_ending} in {last_run}); "
                            "the sweep is closed (DESIGN §7.8)")
            else:
                r.reason = f"no final record yet (last ending {r.last_ending} in {last_run})"
        out[key] = r
    return out, warnings_


def episode_id_of(cell: str, variant: str, template: int, task_cell: str) -> str:
    """The episode id a run of this kind gives template `template` in `task_cell`."""
    tail = "single_turn" if cell == SINGLE_TURN else variant
    return f"main-{template:06d}/{task_cell}/{tail}"


def kind_label(cell: str, variant: str) -> str:
    return {(SINGLE_TURN, BASE): "single-turn control",
            ("F-0", RESTATED): "F-0 restated-at-need"}.get((cell, variant), cell)


def completeness(resolved: dict, templates: int, sweep_closed: bool = False,
                 kinds: tuple = KINDS) -> tuple[list[str], list[str]]:
    """Why the repeat-0 sweep is incomplete for templates 0..templates-1 (empty if complete),
    and, for a closed sweep, its deviations: the keys excluded with no final record and the
    keys never played, per run kind of `kinds` (luna's by default; §13: listed in every
    write-up)."""
    reasons, deviations = [], []
    for cell, variant in kinds:
        cells = NR_TASK_CELLS if cell == SINGLE_TURN else TASK_CELLS
        missing, pending, closed = [], [], Counter()
        for t in range(templates):
            for tc in cells:
                eid = episode_id_of(cell, variant, t, tc)
                r = resolved.get((cell, eid, 0))
                if r is None:
                    missing.append(eid)
                elif r.status == "pending":
                    pending.append(f"{eid}: {r.reason}")
                elif r.closed:
                    closed[str(r.last_ending)] += 1
        n = templates * len(cells)
        label = kind_label(cell, variant)
        if missing and sweep_closed and len(missing) < n:
            deviations.append(f"{label}: {len(missing)} of {n} repeat-0 episodes were never "
                              f"played, and the sweep is closed (first: {missing[0]})")
        elif missing:
            reasons.append(f"{label}: {len(missing)} of {n} repeat-0 episodes have no record "
                           f"(first: {missing[0]})"
                           + (" (no record at all: a run is missing, not a closed sweep)"
                              if sweep_closed else ""))
        if pending:
            reasons.append(f"{label}: {len(pending)} of {n} repeat-0 episodes are pending "
                           f"(first: {pending[0]})")
        if closed:
            deviations.append(
                f"{label}: {sum(closed.values())} of {n} repeat-0 episodes had no final record "
                "and are excluded, the sweep being closed (DESIGN §7.8); last endings: "
                + ", ".join(f"{k} {v}" for k, v in sorted(closed.items())))
    return reasons, deviations


# --- the episode table ---------------------------------------------------------------------

def _carried(cell: str, rec: dict) -> bool | None:
    """S_carried of §2.8 (reading 5): None where it is undefined."""
    if cell not in CARRY_CELLS:
        return None
    payload = rec.get("need_payload") or {}
    if payload.get("S") is not False:
        return None
    retained = bool((payload.get("assistant_carried") or {}).get("carried"))
    bridge = bool((rec.get("need_bridge_carried") or {}).get("carried"))
    return retained or (cell in SUMMARY_CELLS and bridge)


def _num(x) -> float:
    return float("nan") if x is None else float(x)


def _reasoning(usage: dict) -> float:
    """An episode's reasoning tokens: missing (NaN) when the record has them null, as a Messages
    run records a count its responses did not report (R8: null, never 0); 0 when absent."""
    x = usage.get("reasoning_tokens", 0)
    return float("nan") if x is None else float(int(x or 0))


def episode_row(r: Resolved) -> dict:
    rec = r.record
    cell, eid, repeat = r.key
    tc = TaskCell.from_id(rec["task_cell"])
    usage = rec.get("usage") or {}
    need_phase = rec.get("need_phase") or {}
    s_verbatim = (rec.get("need_payload") or {}).get("S") if cell != SINGLE_TURN else None
    carried = _carried(cell, rec)
    s_any = None if s_verbatim is None else bool(s_verbatim or carried)
    models = sorted((rec.get("echo") or {}).get("models_returned") or {})
    return {
        "cell": cell, "variant": rec.get("variant", BASE), "task_cell": tc.id,
        "fact": tc.fact, "recoverable": tc.recoverable, "distance": tc.distance,
        "template": template_index(rec["template_id"]), "repeat": repeat, "episode_id": eid,
        "run_id": r.run_id, "status": r.status, "excluded": r.status != "counted",
        "exclusion_reason": r.reason, "exit_reason": rec.get("exit_reason"),
        "success": int(bool(rec.get("need_correct"))), "need_outcome": rec.get("need_outcome"),
        "n_lookups": int(rec.get("n_lookups") or 0),
        "n_lookups_unavailable": int(rec.get("n_lookups_unavailable") or 0),
        "need_tokens": _num(need_phase.get("tokens")) if need_phase else float("nan"),
        "need_complete": bool(need_phase.get("complete")) if need_phase else False,
        # input_tokens counts cached input on both APIs: the runner adds a Messages
        # response's cache reads and writes to it (pricing.messages_usage_numbers)
        "tokens_total": float(int(usage.get("input_tokens") or 0)
                              + int(usage.get("output_tokens") or 0)),
        "reasoning_tokens": _reasoning(usage),
        "cost_list": _num(rec.get("cost_usd_list")),
        "cost_billed": _num(rec.get("cost_usd_billed_est")),
        "s_verbatim": _num(None if s_verbatim is None else int(bool(s_verbatim))),
        "s_carried": _num(None if carried is None else int(carried)),
        "s_any": _num(None if s_any is None else int(s_any)),
        "compacted_between": _num(rec.get("compacted_between")),
        "models": "|".join(models),
        "stopped": tuple(str(x.get("reason")) for x in rec.get("incomplete") or []),
    }


ROW_COLUMNS = ("cell", "variant", "task_cell", "fact", "recoverable", "distance", "template",
               "repeat", "episode_id", "run_id", "status", "excluded", "exclusion_reason",
               "exit_reason", "success", "need_outcome", "n_lookups", "n_lookups_unavailable",
               "need_tokens", "need_complete", "tokens_total", "reasoning_tokens", "cost_list",
               "cost_billed", "s_verbatim", "s_carried", "s_any", "compacted_between", "models",
               "stopped")
"""The columns of `episode_row`, in order."""


def episode_table(resolved: dict) -> tuple[pd.DataFrame, list[str]]:
    """One row per counted or echo-excluded key (pending and transport-excluded keys have no
    counted record and are counted separately). Also warnings."""
    rows, warn = [], []
    for r in resolved.values():
        if r.record is None:
            continue
        rec = r.record
        if (rec.get("need_outcome") == "correct") != bool(rec.get("need_correct")):
            warn.append(f"{r.run_id}: {r.key[1]!r}: need_correct {rec.get('need_correct')} "
                        f"disagrees with need_outcome {rec.get('need_outcome')!r}; "
                        "need_correct is used")
        row = episode_row(r)
        assert tuple(row) == ROW_COLUMNS
        rows.append(row)
    return pd.DataFrame(rows, columns=list(ROW_COLUMNS)), warn


# --- §2.8: the bug stop ---------------------------------------------------------------------

def need_step_of(rec: dict) -> int | None:
    """The need step from the record's design: the last evidence step plus its gap."""
    d = rec.get("designed") or {}
    ev, gap = d.get("evidence_steps") or [], d.get("gap_steps_latest")
    return None if not ev or gap is None else int(max(ev)) + int(gap)


def far_window_bugs(runs: list[Run]) -> list[str]:
    """Condition 1: a far window-cell episode with S_verbatim = 1 (§2.7)."""
    out = []
    for run in runs:
        if run.cell not in WINDOW_CELLS:
            continue
        for rec in run.records:
            payload = rec.get("need_payload")
            if payload and payload.get("S") is True and rec["task_cell"].endswith("-far"):
                out.append(f"{run.run_id}: {rec['episode_id']!r}: S_verbatim = 1 at far "
                           "distance in a window cell (impossible by §2.7)")
    return out


def _system_tokens(instructions: str, notes: bool, settings: dict) -> tuple[int, str | None]:
    """Project tokens of the system prompt W counts: the request's instructions without the
    notes sentence (D5), or 0 when the run's config does not count it."""
    text = instructions
    if notes:
        suffix = settings["notes_separator"] + NOTES_INSTRUCTION
        if not text.endswith(suffix):
            return 0, "the instructions do not end with the notes sentence"
        text = text[: -len(suffix)]
    if not settings["count_system"]:
        return 0, None
    return tokens.count(text, settings["tokenizer"]), None


def request_parts(payload: dict, api: str = RESPONSES_API) -> tuple[str, list[dict]]:
    """A transcript request's system prompt and input messages, on its API's wire: the
    Responses ``instructions`` and ``input``, or the Messages ``system`` and ``messages``."""
    if api == MESSAGES_API:
        return payload.get("system") or "", payload.get("messages") or []
    return payload.get("instructions") or "", payload.get("input") or []


def reply_counted(response: dict, api: str = RESPONSES_API) -> str:
    """A turn's visible reply as the session kept it and W counted it (harnesses/session.py,
    `Wire.kept_reply`): the Responses message text, or the Messages text blocks, which are the
    empty text for a refusal (its partial text is discarded). A Messages turn with no visible
    reply went back as the ``(no reply)`` placeholder, which is not its reply and counts 0."""
    return MESSAGES.kept_reply(response) if api == MESSAGES_API else output_text(response)


def window_recheck(path: Path, wanted: dict[str, dict], *, notes: bool,
                   settings: dict, api: str = RESPONSES_API) -> dict[str, dict]:
    """§2.8 condition 2 for one window-cell run: for each episode in `wanted` ({episode_id:
    {"need_step", "evidence_steps"}}), the drop-oldest rule replayed on the project-token counts
    of the turns its transcript shows were sent, read on the run's wire (`api`:
    `request_parts`, `reply_counted`). Returns {episode_id: {"S", "keep",
    "user_messages_sent", "user_messages_expected"} or {"problem": why}}."""
    tok = settings["tokenizer"]
    W = settings["W"]
    turns: dict[str, list[tuple]] = defaultdict(list)
    system: dict[str, tuple[int, str | None]] = {}
    users_at: dict[str, dict[int, int]] = defaultdict(dict)
    problems: dict[str, str] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            ev = json.loads(line)
            eid = ev.get("episode_id")
            if eid not in wanted or ev.get("kind") != "step" or eid in problems:
                continue
            payload = ev.get("payload") or {}
            instructions, items = request_parts(payload, api)
            if eid not in system:
                system[eid] = _system_tokens(instructions, notes, settings)
            turn = int(ev["turn"])
            if turn != len(turns[eid]):
                problems[eid] = (f"transcript turn {turn} where turn {len(turns[eid])} was "
                                 "expected (the episode is in the transcript twice, or a turn "
                                 "is missing)")
                continue
            last = items[-1] if items else {}
            if last.get("role") != "user":
                problems[eid] = f"turn {turn}: the request does not end with a user message"
                continue
            obs = tokens.count(item_text(last), tok)
            reply = tokens.count(reply_counted(ev.get("response") or {}, api), tok)
            turns[eid].append((int(ev["pending_step"]), bool(ev["is_lookup_result"]), obs,
                               reply))
            users_at[eid][turn] = sum(1 for i in items if i.get("role") == "user")
    out = {}
    for eid, w in wanted.items():
        if eid in problems:
            out[eid] = {"problem": problems[eid]}
            continue
        seq = turns.get(eid)
        if not seq:
            out[eid] = {"problem": "not in the transcript"}
            continue
        sys_tokens, why = system[eid]
        if why:
            out[eid] = {"problem": why}
            continue

        def first_turn(step, seq=seq):
            return next((i for i, (s, lookup, _, _) in enumerate(seq)
                         if s == step and not lookup), None)

        need_turn = first_turn(w["need_step"])
        evidence = {s: first_turn(s) for s in w["evidence_steps"]}
        if need_turn is None:
            # The runner records need_payload before it sends the need step's first call, and
            # the transcript only after the call returns: an episode stopped by that call has
            # no recorded need request (accounting_check decides whether that can happen)
            out[eid] = {"problem": "the need step's first request is not in the transcript",
                        "need_missing": True}
            continue
        if None in evidence.values():
            out[eid] = {"problem": "an evidence step is not in the transcript"}
            continue
        obs = [x[2] for x in seq]
        rep = [x[3] for x in seq]
        keep = 0
        for j in range(need_turn + 1):
            keep = max(keep, window_keep_start(obs[: j + 1], rep[:j], W, sys_tokens))
        out[eid] = {"S": all(t >= keep for t in evidence.values()), "keep": keep,
                    "need_turn": need_turn,
                    "user_messages_sent": users_at[eid][need_turn],
                    "user_messages_expected": need_turn - keep + 1}
    return out


def accounting_check(runs: list[Run], raw_root: Path, experiment: str = EXPERIMENT,
                     api: str = RESPONSES_API) -> dict:
    """§2.8's two conditions over every window-cell record that reached its need step, the
    transcripts read from raw_root/<experiment>/ on the runs' wire (`api`). Returns
    {"bugs", "warnings", "missing_transcripts", "checked", "runs"}."""
    bugs = far_window_bugs(runs)
    warn, missing, checked, per_run = [], [], 0, []
    for run in runs:
        if run.cell not in WINDOW_CELLS:
            continue
        wanted, expect = {}, {}
        never_reached: Counter = Counter()
        for rec in run.records:
            payload = rec.get("need_payload")
            if not payload or payload.get("S") is None:
                ending = rec.get("exit_reason")
                if ending == "DONE":
                    # a finished episode played its need step, so it must have a payload
                    bugs.append(f"{run.run_id}: {rec['episode_id']!r}: ended DONE with no "
                                "need_payload.S, so §2.8's conditions cannot be checked")
                elif is_final(ending):
                    never_reached[str(ending)] += 1
                continue
            need = need_step_of(rec)
            if need is None:
                bugs.append(f"{run.run_id}: {rec['episode_id']!r}: no evidence steps or need "
                            "step in its record, so §2.8's check cannot be made")
                continue
            wanted[rec["episode_id"]] = {"need_step": need,
                                         "evidence_steps": list(rec["designed"]["evidence_steps"])}
            expect[rec["episode_id"]] = (bool(payload["S"]),
                                         (rec.get("need_info") or {}).get("keep_start"),
                                         rec.get("exit_reason"))
        if never_reached:
            warn.append(f"{run.run_id}: {sum(never_reached.values())} episode(s) with a final "
                        "ending never reached their need step's request (no need_payload), so "
                        "§2.8's conditions do not apply to them: "
                        + ", ".join(f"{k} {v}" for k, v in sorted(never_reached.items())))
        if not wanted:
            continue
        path = raw_root / experiment / run.run_id / "transcript.jsonl.gz"
        if not path.is_file():
            missing.append(run.run_id)
            continue
        got = window_recheck(path, wanted, notes=CELLS[run.cell].notes, settings=run.window,
                             api=api)
        n_keep = n_users = n_stopped = 0
        for eid, (s_verbatim, keep_start, ending) in expect.items():
            g = got[eid]
            if g.get("need_missing") and ending not in FINAL_ENDINGS:
                n_stopped += 1          # stopped by its need step's first call: nothing sent
                continue
            checked += 1
            if "problem" in g:
                bugs.append(f"{run.run_id}: {eid!r}: §2.8's replay cannot be made: "
                            f"{g['problem']}")
                continue
            if g["S"] != s_verbatim:
                bugs.append(f"{run.run_id}: {eid!r}: S_verbatim = {int(s_verbatim)}, but the "
                            f"drop-oldest replay gives {int(g['S'])} (window start "
                            f"{g['keep']}, need turn {g['need_turn']})")
            if keep_start is not None and int(keep_start) != g["keep"]:
                n_keep += 1
            if g["user_messages_sent"] != g["user_messages_expected"]:
                n_users += 1
        if n_keep:
            warn.append(f"{run.run_id}: the replayed window start differs from the runner's "
                        f"need_info.keep_start in {n_keep} episode(s), with S in agreement")
        if n_users:
            warn.append(f"{run.run_id}: the need payload's user messages differ from the "
                        f"replay's count in {n_users} episode(s), with S in agreement")
        if n_stopped:
            warn.append(f"{run.run_id}: {n_stopped} episode(s) stopped at their need step's "
                        "first call (no recorded need request), so §2.8's replay does not "
                        "apply to them")
        per_run.append({"run_id": run.run_id, "episodes_checked": len(expect) - n_stopped,
                        "stopped_at_need_call": n_stopped, "keep_start_differs": n_keep,
                        "user_messages_differ": n_users})
    return {"bugs": bugs, "warnings": warn, "missing_transcripts": missing,
            "checked": checked, "runs": per_run}


# --- the bootstrap and point estimates -----------------------------------------------------

INTEGER_VALUES = ("success", "n_lookups", "need_tokens", "tokens_total", "reasoning_tokens")


class Sample:
    """Per-template sums and counts of one value over a selection of primary episodes. Rows
    whose value is missing (NaN) are left out and counted (`n_missing`)."""

    def __init__(self, df: pd.DataFrame, templates: int, value: str = "success"):
        t = df["template"].to_numpy(int) if len(df) else np.zeros(0, int)
        v = df[value].to_numpy(float) if len(df) else np.zeros(0)
        ok = np.isfinite(v)
        self.n_missing = int((~ok).sum())
        t, v = t[ok], v[ok]
        self.n = np.bincount(t, minlength=templates).astype(float)
        self.s = np.bincount(t, weights=v, minlength=templates)
        self.count = len(v)
        self.total = float(v.sum())
        self.exact = value in INTEGER_VALUES
        self._boot: np.ndarray | None = None
        self._boot_idx: np.ndarray | None = None

    def point(self) -> Fraction | float | None:
        if self.count == 0:
            return None
        if self.exact:
            return Fraction(round(self.total), self.count)
        return self.total / self.count

    def boot(self, idx: np.ndarray) -> np.ndarray:
        """The mean in each resample (NaN where the resample holds no episode). Cached for the
        resamples it was last called with only."""
        if self._boot is None or self._boot_idx is not idx:
            num, den = self.s[idx].sum(axis=1), self.n[idx].sum(axis=1)
            out = np.full(len(num), np.nan)
            ok = den > 0
            out[ok] = num[ok] / den[ok]
            self._boot, self._boot_idx = out, idx
        return self._boot


def resample_indices(templates: int, seed: int, boot: int) -> np.ndarray:
    """`boot` resamples of templates 0..templates-1 with replacement (§9.1)."""
    return np.random.default_rng(seed).integers(0, templates, size=(boot, templates))


def _f(x) -> float | None:
    return None if x is None else float(x)


def _exact(x) -> str | None:
    return str(x) if isinstance(x, Fraction) else None


def interval(dist: np.ndarray, level: float) -> list[float] | None:
    ok = dist[np.isfinite(dist)]
    if len(ok) == 0:
        return None
    lo, hi = np.quantile(ok, [(1 - level) / 2, (1 + level) / 2])
    return [float(lo), float(hi)]


def summarise(point, dist: np.ndarray) -> dict:
    """A point estimate with its percentile 90% and 95% intervals."""
    return {"estimate": _f(point), "exact": _exact(point),
            "ci90": interval(dist, 0.90), "ci95": interval(dist, 0.95),
            "undefined_resamples": int(np.sum(~np.isfinite(dist)))}


def p_null_le(dist: np.ndarray, threshold: float) -> float | None:
    """One-sided bootstrap p-value for H0: contrast <= threshold (ties on the null side)."""
    ok = dist[np.isfinite(dist)]
    return None if len(ok) == 0 else float(np.mean(ok <= threshold + TOL))


def p_null_ge(dist: np.ndarray, threshold: float) -> float | None:
    """One-sided bootstrap p-value for H0: contrast >= threshold (ties on the null side)."""
    ok = dist[np.isfinite(dist)]
    return None if len(ok) == 0 else float(np.mean(ok >= threshold - TOL))


def _diff(a, b):
    return None if a is None or b is None else a - b


def _ratio(a, b):
    return None if a is None or b is None or b == 0 else a / b


def _ratio_dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = a / b
    out[~np.isfinite(out)] = np.nan
    return out


# --- readings (pure functions, so their boundaries can be tested) --------------------------

def manipulation_met(penalty_nr: Fraction) -> bool:
    """§3 H1: Penalty_NR >= 25pp (point estimate)."""
    return penalty_nr >= MANIPULATION_MIN


def recoverable_within(penalty_r: Fraction) -> bool:
    """§3 H1: |Penalty_R| <= 5pp (point estimate)."""
    return abs(penalty_r) <= RECOVERABLE_BAND


def ratio_met(ratio: Fraction) -> bool:
    """§3 H1: the lookups ratio and R_need >= 1.30 (point estimate)."""
    return ratio >= RATIO_MIN


def h1_kill(delta: Fraction, upper90: float) -> bool:
    """§3 H1's kill, as written: Delta_H1 < 10pp and the 90% upper bound < 15pp."""
    return delta < KILL_POINT and upper90 < KILL_UPPER - TOL


def h3_holds(upper90: float) -> bool:
    """§3 H3: the upper bound of the 90% CI of Delta_H3 is <= 5pp."""
    return upper90 <= float(H3_MARGIN) + TOL


def holm(pvalues: list[float], alpha: float = ALPHA) -> dict:
    """Holm's step-down procedure (``ps.holm_reject``) with the adjusted p-values."""
    p = [1.0 if x is None else float(x) for x in pvalues]
    reject = ps.holm_reject(p, alpha)
    adjusted = [0.0] * len(p)
    running = 0.0
    for i, j in enumerate(np.argsort(p, kind="stable")):
        running = max(running, min(1.0, (len(p) - i) * p[j]))
        adjusted[j] = running
    return {"pvalues": p, "reject": [bool(x) for x in reject], "adjusted": adjusted,
            "alpha": alpha}


MODEL_DISAGREES = "inconclusive: the Holm test rejects, but the model check does not agree"


def h1_verdict(supported: bool, killed: bool, holm_rejects: bool = False) -> str:
    """H1 in the wording of `results/decisions.md` (2026-10-10): supported, the kill rule
    fires, both, or inconclusive (saying so when only the model check stood in the way)."""
    if supported and killed:
        return "supported (Δ_H1 > 0), and the kill rule fires"
    if supported:
        return "supported"
    if killed:
        return "kill rule fires"
    return MODEL_DISAGREES if holm_rejects else "inconclusive"


def h3_verdict(supported: bool, lower90: float | None, holm_rejects: bool = False) -> str:
    """H3 (no kill rule): supported; not supported with the whole 90% CI above 5pp, against
    the prediction (reading 16); or inconclusive."""
    if supported:
        return "supported"
    if lower90 is not None and lower90 > float(H3_MARGIN) + TOL:
        return ("not supported: the whole 90% CI of Δ_H3 lies above 5pp, against the "
                "prediction")
    return MODEL_DISAGREES if holm_rejects else "inconclusive"


# --- GLMs (§9.1, §9.4) ---------------------------------------------------------------------

def informative(y: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``ps._informative``'s selection: (row mask, template codes 0..G-1 of the kept rows, the
    group label of each code), in the same order."""
    codes0, uniq = pd.factorize(groups)
    sums = np.bincount(codes0, weights=y, minlength=len(uniq))
    counts = np.bincount(codes0, minlength=len(uniq))
    keep = ((sums > 0) & (sums < counts))[codes0]
    codes, kept = pd.factorize(codes0[keep])
    return keep, codes, np.asarray(uniq)[kept]


def _wald(est: float, se: float | None) -> dict:
    if se is None or not math.isfinite(se) or se <= 0:
        return {"se": None, "z": None, "p_two_sided": None, "ci90": None, "ci95": None}
    z = est / se
    return {"se": se, "z": z, "p_two_sided": float(2 * special.ndtr(-abs(z))),
            "ci90": [est - Z90 * se, est + Z90 * se], "ci95": [est - Z95 * se, est + Z95 * se]}


def _sign(x: float) -> int:
    """The sign of a model estimate, with power_sim's 1e-8 threshold for "positive"."""
    return 1 if x > GLM_SIGN_EPS else -1 if x < -GLM_SIGN_EPS else 0


def sm_fe_logit(y: np.ndarray, codes: np.ndarray, z: np.ndarray) -> dict | None:
    """statsmodels' binomial GLM of y on template dummies (codes 0..G-1) and the columns of z,
    as §9.1 specifies it: IRLS with statsmodels' defaults, and the covariance clustered by
    template without statsmodels' small-sample correction, times G/(G - 1) (§9.1, D25).
    Returns the template intercepts, the slopes, the slopes' covariance (NaN where statsmodels
    gives none, for example under quasi-separation) and statsmodels' convergence flag; None if
    the fit fails or a coefficient is not finite. With one template there is no clustered
    covariance (G/(G - 1) is undefined), and the covariance is NaN."""
    g = int(codes.max()) + 1
    dummies = np.zeros((len(y), g))
    dummies[np.arange(len(y)), codes] = 1.0
    try:
        with warnings.catch_warnings(), np.errstate(all="ignore"):
            warnings.simplefilter("ignore")
            res = sm.GLM(y, np.column_stack([dummies, z]), family=sm.families.Binomial()).fit(
                cov_type="cluster", cov_kwds={"groups": codes, "use_correction": False})
    except (np.linalg.LinAlgError, ValueError, FloatingPointError,
            sm_exceptions.PerfectSeparationError):
        return None
    params = np.asarray(res.params, float)
    if not np.isfinite(params).all():
        return None
    k = params.size - g
    cov = (np.asarray(res.cov_params(), float)[g:, g:] * g / (g - 1) if g > 1
           else np.full((k, k), np.nan))
    return {"alpha": params[:g], "beta": params[g:], "cov": cov,
            "converged": bool(res.converged)}


def _contrast_se(cov: np.ndarray, weights: dict[str, float], names: list[str]) -> float | None:
    c = np.zeros(len(names))
    for name, w in weights.items():
        c[names.index(name)] = w
    var = float(c @ cov @ c)
    return math.sqrt(var) if math.isfinite(var) and var > 0 else None


def emulate(y: np.ndarray, codes: np.ndarray, z: np.ndarray
            ) -> tuple[tuple[np.ndarray, np.ndarray] | None, str | None]:
    """power_sim's emulation of a fixed-effects logit (`ps._fe_logit_mle`) and the route it
    took: "newton" when its own Newton steps gave finite values, "statsmodels" when they did
    not and it fell back to statsmodels, so that it is no independent check; None if neither."""
    with np.errstate(all="ignore"):
        try:
            alpha, beta = ps._fe_logit_newton(y, codes, z, dev_tol=1e-8)
            if np.isfinite(alpha).all() and np.isfinite(beta).all():
                return (alpha, beta), "newton"
        except (np.linalg.LinAlgError, ValueError, FloatingPointError):
            pass
    fit = ps._fe_logit_mle(y, codes, z, engine="statsmodels")
    return fit, None if fit is None else "statsmodels"


def fe_logit_fit(y: np.ndarray, groups: np.ndarray, z: np.ndarray, names: list[str],
                 contrasts: dict[str, dict[str, float]] | None = None) -> dict:
    """A logit with template fixed effects on the templates with outcome variation, fitted by
    statsmodels (`sm_fe_logit`): the coefficients; the last column's estimate with its
    cluster-robust Wald quantities; each of `contrasts` ({name: {coefficient: weight}}, a linear
    combination of the coefficients) likewise; and power_sim's Newton emulation of the same fit
    (`ps._fe_logit_mle`) as a cross-check, with the route it took (`emulate`). The template
    intercepts are kept under the private key "_alpha" ({template: intercept}), which the
    output leaves out.

    One template with outcome variation is enough for the point estimates; the cluster-robust
    Wald quantities need two. Until 2026-10-10 the fit needed two templates for anything, which
    left H3's model check on luna's sweep (one template with outcome variation) with no
    estimate; the researcher's decision of 2026-10-10 (results/decisions.md) dropped that."""
    y = np.asarray(y, float)
    z = np.asarray(z, float)
    keep, codes, labels = informative(y, groups)
    out = {"n_rows": len(y), "n_templates": len(pd.unique(groups)),
           "n_templates_informative": int(codes.max() + 1) if len(codes) else 0,
           "n_rows_fitted": int(keep.sum()), "coefficients": None, "target": names[-1],
           "estimate": None, "se_available": False, "fitted_by": "statsmodels GLM (§9.1)",
           "contrasts": {}, "estimate_emulated": None, "emulated_sign_disagrees": False,
           **_wald(0.0, None)}
    out["n_templates_dropped"] = out["n_templates"] - out["n_templates_informative"]
    if out["n_templates_informative"] < 1:
        out["note"] = "no template with outcome variation: no fit"
        return out
    fit = sm_fe_logit(y[keep], codes, z[keep])
    if fit is None:
        out["note"] = "the statsmodels fit failed"
        return out
    beta, cov = fit["beta"], fit["cov"]
    out["coefficients"] = dict(zip(names, (float(b) for b in beta), strict=True))
    out["estimate"] = float(beta[-1])
    out["converged"] = fit["converged"]
    out.update(_wald(out["estimate"], _contrast_se(cov, {names[-1]: 1.0}, names)))
    out["se_available"] = out["se"] is not None
    if out["n_templates_informative"] < 2:
        out["note"] = ("one template with outcome variation: point estimates only, no "
                       "cluster-robust SE")
    elif not out["se_available"]:
        out["note"] = ("statsmodels gives no finite cluster-robust SE (for example under "
                       "quasi-separation)")
    for name, weights in (contrasts or {}).items():
        est = float(sum(w * out["coefficients"][c] for c, w in weights.items()))
        out["contrasts"][name] = {"estimate": est,
                                  **_wald(est, _contrast_se(cov, weights, names))}
    out["_alpha"] = dict(zip(labels.tolist(), (float(a) for a in fit["alpha"]), strict=True))
    emu, out["emulation_route"] = emulate(y[keep], codes, z[keep])
    if emu is not None:
        out["estimate_emulated"] = float(emu[1][-1])
        out["emulated_sign_disagrees"] = (_sign(out["estimate"])
                                          != _sign(out["estimate_emulated"]))
    return out


def firth_fe_logit(y: np.ndarray, codes: np.ndarray, z: np.ndarray, max_iter: int = 1000,
                   tol: float = 1e-8) -> tuple[np.ndarray, np.ndarray] | None:
    """Firth's penalized-likelihood logit (Firth 1993; Heinze and Schemper 2002) with template
    fixed effects: it maximises the log-likelihood plus half the log-determinant of the Fisher
    information, which keeps every coefficient finite under separation. Newton steps on the
    modified score X'(y - mu + h (1/2 - mu)), h the hat values, with step halving on the
    penalized log-likelihood. Returns (template intercepts, slopes), or None if it does not
    converge. Used under H1_SEPARATION_RULE = "firth", the researcher's ruling of 2026-10-10.
    Checked against a direct numerical maximisation of the penalized log-likelihood in the
    tests (to < 1e-7 on every coefficient).

    The steps use the Fisher information of the likelihood, not the Hessian of the penalized
    log-likelihood, so convergence is linear: on luna's sweep, with most cells at 100%, the
    fit took 103 steps to reach `tol`. The cap was 100 until 2026-10-10, when that sweep's
    FINAL analysis (`results/persistgym_h1h3/20261010T205230Z/`) returned "did not converge";
    it is 1,000 since (the researcher's decision of 2026-10-10, results/decisions.md)."""
    y = np.asarray(y, float)
    g = int(codes.max()) + 1
    x = np.column_stack([np.eye(g)[codes], np.asarray(z, float)])

    def penalized(theta):
        eta = x @ theta
        mu = special.expit(eta)
        w = mu * (1 - mu)
        ll = -float(np.sum(y * np.logaddexp(0.0, -eta) + (1 - y) * np.logaddexp(0.0, eta)))
        try:
            chol = linalg.cho_factor(x.T @ (x * w[:, None]), lower=True)
        except np.linalg.LinAlgError:
            return -np.inf, None, mu, w
        return ll + float(np.sum(np.log(np.diag(chol[0])))), chol, mu, w

    theta = np.zeros(x.shape[1])
    value, chol, mu, w = penalized(theta)
    for _ in range(max_iter):
        if chol is None:
            return None
        v = linalg.solve_triangular(chol[0], x.T, lower=True)
        h = w * np.sum(v * v, axis=0)
        step = linalg.cho_solve(chol, x.T @ (y - mu + h * (0.5 - mu)))
        t = 1.0
        while True:
            new = penalized(theta + t * step)
            if new[0] >= value - 1e-10 or t < 1e-8:
                break
            t /= 2
        theta = theta + t * step
        value, chol, mu, w = new
        if np.max(np.abs(t * step)) < tol:
            return (theta[:g], theta[g:]) if np.isfinite(theta).all() else None
    return None


def factorial_design(harness: dict[str, np.ndarray], R: np.ndarray, D: np.ndarray,
                     N: np.ndarray, target: str) -> tuple[np.ndarray, list[str]]:
    """The saturated harness x recoverable x derived x near design (no intercept: the
    template fixed effects hold it), the `target` column last. Reference: F-0, not
    recoverable, observed, far."""
    base = {"R": R, "D": D, "N": N}
    cols: dict[str, np.ndarray] = {}
    for k in (1, 2, 3):
        for combo in combinations("RDN", k):
            cols[":".join(combo)] = np.prod([base[c] for c in combo], axis=0)
    for h, hv in harness.items():
        cols[h] = hv
        for k in (1, 2, 3):
            for combo in combinations("RDN", k):
                cols[f"{h}:" + ":".join(combo)] = hv * np.prod([base[c] for c in combo], axis=0)
    names = [c for c in cols if c != target] + [target]
    return np.column_stack([cols[c].astype(float) for c in names]), names


def _separation(fitted: pd.DataFrame, by: list[str]) -> list[str]:
    """Cells of a GLM's fitted rows (its templates with outcome variation) whose outcomes are
    all equal: their logit-scale effects are infinite (quasi-separation)."""
    out = []
    for name, g in fitted.groupby(by, sort=True):
        if g["success"].nunique() == 1:
            out.append(f"{' '.join(map(str, name if isinstance(name, tuple) else (name,)))}: "
                       f"all {int(g['success'].iloc[0])} ({len(g)} episodes)")
    return out


def logit_status(fitted: pd.DataFrame, parts: list[tuple[str, pd.Series, int]]) -> dict:
    """Whether a logit-scale contrast is finite, from a GLM's fitted rows (ruled item 1).
    `parts` are (label, row mask, sign of that part's logit in the contrast). A part whose
    rows are all 1 has logit +inf, all 0 -inf; the contrast is then +inf or -inf when every
    such part pushes it the same way, and undefined (inf - inf) when they push both ways or a
    part has no rows. Returns {"status", "no_variation": the parts' descriptions}."""
    directions, notes = set(), []
    for label, mask, sign in parts:
        y = fitted.loc[mask, "success"]
        if len(y) == 0:
            directions.add(0)
            notes.append(f"{label}: no episodes")
        elif y.nunique() == 1:
            v = int(y.iloc[0])
            directions.add(sign if v == 1 else -sign)
            notes.append(f"{label}: all {v} ({len(y)} episodes)")
    if 0 in directions or directions == {1, -1}:
        status = UNDEFINED
    elif directions == {1}:
        status = PLUS_INF
    elif directions == {-1}:
        status = MINUS_INF
    else:
        status = FINITE
    return {"status": status, "no_variation": notes}


def _glm_91_rows(prim: pd.DataFrame, harness: tuple[str, ...]) -> tuple[pd.DataFrame,
                                                                         np.ndarray, list[str]]:
    sub = prim[(prim.variant == BASE) & prim.cell.isin(("F-0", *harness))]
    z, names = factorial_design({h: (sub.cell == h).to_numpy() for h in harness},
                                sub.recoverable.to_numpy(bool).astype(float),
                                (sub.fact == "derived").to_numpy().astype(float),
                                (sub.distance == "near").to_numpy().astype(float),
                                target=f"{harness[0]}:R")
    return sub, z, names


def logit_sign(glm: dict) -> int | None:
    """The sign of a GLM's target coefficient: its estimate's when finite, the limit's when
    +inf or -inf (`logit_status`), None when undefined or not fitted."""
    est, status = glm.get("estimate"), glm.get("logit_status", FINITE)
    if est is None:
        return None
    return {FINITE: _sign(est), PLUS_INF: 1, MINUS_INF: -1}.get(status)


def glm_91(prim: pd.DataFrame, harness: tuple[str, ...] = ("W-0",)) -> dict:
    """§9.1's confirmatory GLM on F-0 and `harness` (base, all 8 task cells): its W-0 x R
    coefficient is the logit-scale Delta_H1 (ruled item 2), its W-0 coefficient minus
    Penalty_NR and W-0 plus W-0 x R minus Penalty_R, on the logit scale. Also whether the
    logit-scale Delta_H1 is finite, from H1's 4 cells among the fitted rows (`logit_status`)."""
    sub, z, names = _glm_91_rows(prim, harness)
    w = harness[0]
    out = fe_logit_fit(sub["success"].to_numpy(float), sub["template"].to_numpy(), z, names,
                       contrasts={"penalty_nr_logit": {w: -1.0},
                                  "penalty_r_logit": {w: -1.0, f"{w}:R": -1.0}})
    out["cells"] = ["F-0", *harness]
    keep, _, _ = informative(sub["success"].to_numpy(float), sub["template"].to_numpy())
    fitted = sub[keep]
    out["no_variation_cells"] = _separation(fitted, ["cell", "task_cell"])
    status = logit_status(fitted, [
        (f"{c} {tc}", (fitted.cell == c) & (fitted.task_cell == tc), sign)
        for c, tc, sign in (("F-0", OBS_NR_FAR, 1), (w, OBS_NR_FAR, -1),
                            ("F-0", OBS_R_FAR, -1), (w, OBS_R_FAR, 1))])
    out["logit_status"] = status["status"]
    out["h1_cells_no_variation"] = status["no_variation"]
    for name, tc in (("penalty_nr_logit", OBS_NR_FAR), ("penalty_r_logit", OBS_R_FAR)):
        if name in out["contrasts"]:
            out["contrasts"][name]["logit_status"] = logit_status(fitted, [
                (f"{c} {tc}", (fitted.cell == c) & (fitted.task_cell == tc), sign)
                for c, sign in (("F-0", 1), (w, -1))])["status"]
    return out


def glm_91_firth(prim: pd.DataFrame) -> dict:
    """The W-0 x R coefficient of a Firth-penalized fit of the §9.1 GLM, on the same rows
    (`firth_fe_logit`): the templates with outcome variation, as in the ordinary fit. Fitted
    when the logit-scale Delta_H1 is not finite; read by H1_SEPARATION_RULE = "firth", the rule
    in force (the ruling of 2026-10-10), or else by its sensitivity line."""
    sub, z, _ = _glm_91_rows(prim, ("W-0",))
    y = sub["success"].to_numpy(float)
    keep, codes, _ = informative(y, sub["template"].to_numpy())
    if not len(codes) or codes.max() + 1 < 2:
        return {"estimate": None, "note": "fewer than 2 templates with outcome variation"}
    fit = firth_fe_logit(y[keep], codes, z[keep])
    return {"estimate": None if fit is None else float(fit[1][-1]),
            "note": None if fit is not None else "the Firth fit did not converge"}


def h1_standin(prim: pd.DataFrame) -> dict:
    """power_sim's stand-in (``ps.h1_glm``), on H1's 4 cells: template fixed effects, W, R and
    W x R; its last coefficient is the logit-scale Delta_H1."""
    sub = prim[(prim.variant == BASE) & prim.cell.isin(("F-0", "W-0"))
               & prim.task_cell.isin((OBS_NR_FAR, OBS_R_FAR))]
    w = (sub.cell == "W-0").to_numpy(float)
    r = sub.recoverable.to_numpy(bool).astype(float)
    y = sub["success"].to_numpy(float)
    keep, codes, _ = informative(y, sub["template"].to_numpy())
    n = int(codes.max() + 1) if len(codes) else 0
    if n < 2:
        return {"estimate": None, "note": "fewer than 2 templates with outcome variation"}
    mle = ps._fe_logit_mle(y[keep], codes, np.column_stack([w, r, w * r])[keep])
    return {"estimate": None if mle is None else float(mle[1][-1]),
            "n_templates_informative": n}


def _h3_rows(prim: pd.DataFrame) -> pd.DataFrame:
    return prim[(((prim.cell == "F-0") & (prim.variant == BASE)) | (prim.cell == SINGLE_TURN))
                & prim.task_cell.isin(H3_CELLS)]


def _ame(pairs: pd.DataFrame, a_of: dict, gamma: float, arm: float) -> dict:
    """The arm's average marginal effect over every (template, task cell) pair, a template
    without a fitted intercept (no outcome variation) adding 0 (reading 15), and over the
    pairs of the fitted templates only."""
    total, n_fitted = 0.0, 0
    for t, tc in pairs.itertuples(index=False):
        if t in a_of:
            base = a_of[t] + (gamma if tc.startswith("derived") else 0.0)
            total += float(special.expit(base + arm) - special.expit(base))
            n_fitted += 1
    ame = total / len(pairs) if len(pairs) else None
    inf = total / n_fitted if n_fitted else None
    return {"ame": ame if ame is not None and math.isfinite(ame) else None,
            "ame_informative": inf if inf is not None and math.isfinite(inf) else None,
            "n_pairs": len(pairs), "n_pairs_informative": n_fitted}


def h3_glm_literal(prim: pd.DataFrame) -> dict:
    """§9.4's model check for H3, as registered: a binomial GLM (statsmodels) with template
    fixed effects and the arm indicator (single-turn vs F-0) on the H3 cells. Its arm
    coefficient is the logit-scale Delta_H3 (with whether it is finite, `logit_status`), and
    its average marginal effect the probability-scale one (`_ame`, reading 15). One template
    with outcome variation is enough (`fe_logit_fit`; the decision of 2026-10-10)."""
    sub = _h3_rows(prim)
    arm = (sub.cell == SINGLE_TURN).to_numpy(float)
    y = sub["success"].to_numpy(float)
    groups = sub["template"].to_numpy()
    out = fe_logit_fit(y, groups, arm[:, None], ["arm"])
    out["model"] = "§9.4: template fixed effects + arm (statsmodels)"
    pairs = sub[["template", "task_cell"]].drop_duplicates()
    keep, _, _ = informative(y, groups)
    fitted = sub[keep]
    status = logit_status(fitted, [("single-turn", fitted.cell == SINGLE_TURN, 1),
                                   ("F-0", fitted.cell == "F-0", -1)])
    out["logit_status"] = status["status"]
    out["arm_no_variation"] = status["no_variation"]
    if out["coefficients"] is None:
        none = out["n_templates_informative"] == 0 and len(pairs)
        varies = set(fitted["template"].tolist())
        out.update(ame=0.0 if none else None, ame_informative=None, n_pairs=len(pairs),
                   n_pairs_informative=int(pairs["template"].isin(varies).sum()))
        return out
    out.update(_ame(pairs, out["_alpha"], 0.0, out["estimate"]))
    return out


def h3_glm_powersim(prim: pd.DataFrame) -> dict:
    """power_sim's model check for H3 (``ps.h3_glm_ame``, generalised to unequal cells): template
    fixed effects, a derived-cell term and the arm, fitted by power_sim's emulation, and its
    average marginal effect as in `h3_glm_literal`. A sensitivity analysis here (B1). As for
    the registered model, one template with outcome variation is enough here (the decision of
    2026-10-10); power_sim's own ``h3_glm_ame``, which the simulation used, needs two."""
    sub = _h3_rows(prim)
    z = np.column_stack([(sub.fact == "derived").to_numpy(float),
                         (sub.cell == SINGLE_TURN).to_numpy(float)])
    y = sub["success"].to_numpy(float)
    keep, codes, labels = informative(y, sub["template"].to_numpy())
    pairs = sub[["template", "task_cell"]].drop_duplicates()
    n = int(codes.max() + 1) if len(codes) else 0
    out = {"model": "power_sim's: template fixed effects + derived term + arm (emulation)",
           "n_templates_informative": n, "arm_logit": None, "ame": None,
           "ame_informative": None, "n_pairs": len(pairs), "emulation_route": None}
    if n < 1:
        out["ame"] = 0.0 if len(pairs) else None
        return out
    mle, out["emulation_route"] = emulate(y[keep], codes, z[keep])
    if mle is None:
        return out
    alpha, beta = mle
    a_of = dict(zip(labels.tolist(), alpha.tolist(), strict=True))
    out.update(_ame(pairs, a_of, float(beta[0]), float(beta[1])))
    out["arm_logit"] = float(beta[1])
    return out


# --- §9.5 cost outcomes --------------------------------------------------------------------

def fe_poisson(y: np.ndarray, groups: np.ndarray, x: np.ndarray, names: list[str]) -> dict:
    """Log-link Poisson GLM (quasi-Poisson variance) with template fixed effects and a
    template-clustered sandwich with the G/(G - 1) factor; ratios exp(beta). Templates whose
    outcome is 0 in every row are dropped (their fixed effect is -inf). A cell with no events
    at all has ratio 0 and no interval, and is left out of the fit; with no events in the
    reference cell (the rows of no column) no ratio is finite, and there is no fit. The
    sandwich does not use the dispersion; the Pearson dispersion is reported."""
    y = np.asarray(y, float)
    x = np.asarray(x, float)
    ok = np.isfinite(y)
    y, x, groups = y[ok], x[ok], np.asarray(groups)[ok]
    out = {"n_rows": len(y), "ratios": {}}
    zero = [j for j in range(x.shape[1]) if x[:, j].any() and y[x[:, j] > 0].sum() <= 0]
    for j in zero:
        out["ratios"][names[j]] = {"beta": None, "ratio": 0.0, "se": None, "ratio_ci95": None,
                                   "ratio_ci90": None, "p_two_sided": None,
                                   "note": "no events in this cell: ratio 0, no interval"}
    rows = ~x[:, zero].any(axis=1) if zero else np.ones(len(y), bool)
    y, x, groups = y[rows], x[rows], groups[rows]
    reference = ~x.any(axis=1)
    if reference.any() and y[reference].sum() <= 0:
        out["note"] = "no events in the reference cell (F-0): no ratio is finite"
        return out
    codes0, uniq = pd.factorize(groups)
    tot = np.bincount(codes0, weights=y, minlength=len(uniq))
    keep = (tot > 0)[codes0]
    out.update(n_templates=len(uniq), n_templates_all_zero=int(np.sum(tot <= 0)))
    y, x = y[keep], x[keep]
    codes, _ = pd.factorize(codes0[keep])
    present = [j for j in range(x.shape[1]) if x[:, j].any()]
    x = x[:, present]
    g = int(codes.max() + 1) if len(codes) else 0
    k = x.shape[1]
    if g < 2 or k == 0 or len(y) <= g + k:
        out["note"] = "too few templates with a nonzero outcome to fit"
        return out
    dummies = np.zeros((len(y), g))
    dummies[np.arange(len(y)), codes] = 1.0
    X = np.column_stack([dummies, x])
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = sm.GLM(y, X, family=sm.families.Poisson()).fit()
        mu = np.asarray(res.mu)
        hess = X.T @ (X * mu[:, None])
        h_inv = np.linalg.inv(hess)
        scores = np.zeros((g, X.shape[1]))
        np.add.at(scores, codes, X * (y - mu)[:, None])
        cov = h_inv @ (scores.T @ scores) @ h_inv * g / (g - 1)
    except (np.linalg.LinAlgError, ValueError, FloatingPointError) as e:
        out["note"] = f"the fit failed: {type(e).__name__}"
        return out
    beta = np.asarray(res.params)[g:]
    se = np.sqrt(np.clip(np.diag(cov)[g:], 0.0, None))
    out["dispersion_pearson"] = float(np.sum((y - mu) ** 2 / mu) / (len(y) - g - k))
    for j, b, s in zip(present, beta, se, strict=True):
        w = _wald(float(b), float(s))
        out["ratios"][names[j]] = {
            "beta": float(b), "ratio": float(np.exp(b)), "se": w["se"],
            "ratio_ci95": None if w["ci95"] is None else [float(np.exp(v)) for v in w["ci95"]],
            "ratio_ci90": None if w["ci90"] is None else [float(np.exp(v)) for v in w["ci90"]],
            "p_two_sided": w["p_two_sided"]}
    return out


def cost_outcomes(prim: pd.DataFrame, cells: tuple[str, ...] = HARNESS_CELLS) -> list[dict]:
    """§9.5 per task cell and outcome: each harness cell of `cells` against F-0 (reading 11).
    An outcome missing in some episodes (Haiku's unreported reasoning tokens, R8) is fitted on
    the others, and the count is given; missing in all, it is unavailable."""
    others = [c for c in cells if c != "F-0"]
    rows = []
    for tc in TASK_CELLS:
        sub = prim[(prim.variant == BASE) & prim.cell.isin(cells) & (prim.task_cell == tc)]
        x = np.column_stack([(sub.cell == c).to_numpy(float) for c in others])
        for outcome, label in COST_OUTCOMES.items():
            means = {c: _f(sub[sub.cell == c][outcome].mean()) if (sub.cell == c).any()
                     else None for c in cells}
            fit = fe_poisson(sub[outcome].to_numpy(float), sub["template"].to_numpy(), x,
                             others)
            row = {"task_cell": tc, "outcome": outcome, "label": label, "means": means, **fit}
            missing = int(sub[outcome].isna().sum())
            if missing:
                row["n_missing"] = missing
                if missing == len(sub):
                    row["unavailable"] = ("missing in every episode (not reported by the "
                                          "provider): no ratio")
            rows.append(row)
    return rows


# --- the analysis --------------------------------------------------------------------------

class Analysis:
    """The primary episodes (repeat 0, counted, templates 0..T-1) and the shared resamples."""

    def __init__(self, prim: pd.DataFrame, templates: int, idx: np.ndarray):
        self.prim, self.templates, self.idx = prim, templates, idx

    def sample(self, cell: str, task_cells, value: str = "success", variant: str = BASE,
               mask: pd.Series | None = None) -> Sample:
        cells = (task_cells,) if isinstance(task_cells, str) else tuple(task_cells)
        p = self.prim
        sel = (p.cell == cell) & (p.variant == variant) & p.task_cell.isin(cells)
        if mask is not None:
            sel &= mask
        return Sample(p[sel], self.templates, value)


def rate(s: Sample) -> dict:
    return {"n": s.count, "successes": round(s.total), "rate": _f(s.point()),
            "exact": _exact(s.point())}


def h1_model_check(glm: dict, delta, rule: str | None = None,
                   firth: dict | None = None) -> dict:
    """§9.4's model check for H1: the §9.1 GLM's logit-scale Delta_H1 is positive. When it is
    not finite (an H1 cell without outcome variation), `rule` (default `H1_SEPARATION_RULE`,
    "firth" by the ruling of 2026-10-10, ruled item 1) decides: "literal" reads the limit's
    sign (+inf agrees; -inf and an undefined sign do not), "firth" a Firth-penalized fit's sign
    (`firth`), and "probability-scale" the probability-scale Delta_H1's sign (`delta`)."""
    rule = rule or H1_SEPARATION_RULE
    if rule not in H1_SEPARATION_RULES:
        raise ValueError(f"unknown H1 separation rule {rule!r}")
    est, status = glm.get("estimate"), glm.get("logit_status", FINITE)
    out = {"model": "§9.1 confirmatory GLM (statsmodels), W-0 x R: the logit-scale Δ_H1",
           "rule": rule, "estimate": est, "logit_status": status,
           "h1_cells_no_variation": glm.get("h1_cells_no_variation") or []}
    if est is None:
        out.update(agrees=False, sign=None, basis="the §9.1 GLM could not be fitted")
    elif status == FINITE:
        out.update(agrees=est > GLM_SIGN_EPS, sign=_sign(est),
                   basis="the §9.1 GLM's W-0 x R coefficient")
    elif rule == "literal":
        sign = {PLUS_INF: 1, MINUS_INF: -1}.get(status)
        out.update(agrees=status == PLUS_INF and est > GLM_SIGN_EPS, sign=sign,
                   basis=("the sign of the logit-scale Δ_H1's limit, from the cells without "
                          "outcome variation (rule 'literal'; an undefined sign does not "
                          "agree)"))
    elif rule == "firth":
        fe = (firth or {}).get("estimate")
        out.update(agrees=fe is not None and fe > GLM_SIGN_EPS,
                   sign=None if fe is None else _sign(fe), firth_estimate=fe,
                   basis="a Firth-penalized fit of the §9.1 GLM (rule 'firth')")
    else:
        out.update(agrees=delta is not None and delta > 0, sign=None,
                   basis=("not applicable: an H1 cell has no outcome variation, so the "
                          "probability-scale sign is read (rule 'probability-scale')"))
    return out


def h1_rule_sensitivity(glm: dict, delta, in_force: str, firth: dict | None = None) -> dict:
    """What H1's model check would read under each rule not in force: the sensitivity lines of
    the ruling of 2026-10-10 (ruled item 1). They enter no decision. Empty when the §9.1 GLM
    was not fitted or its logit-scale Delta_H1 is finite: every rule then reads the same."""
    if glm.get("estimate") is None or glm.get("logit_status", FINITE) == FINITE:
        return {}
    keys = ("agrees", "sign", "basis", "firth_estimate")
    return {rule: {k: v for k, v in h1_model_check(glm, delta, rule, firth).items() if k in keys}
            for rule in H1_SEPARATION_RULES if rule != in_force}


def h1_reading(an: Analysis, glm: dict, standin: dict, firth: dict | None = None,
               w_n_0: bool = True) -> dict:
    """§3 H1 (above), with W-n-0 alongside; with `w_n_0` False (Haiku's W-n-0 cut by R8's size
    rule) W-n-0 is reported as not run."""
    idx = an.idx
    s = {"F-0 NR": an.sample("F-0", OBS_NR_FAR), "W-0 NR": an.sample("W-0", OBS_NR_FAR),
         "F-0 R": an.sample("F-0", OBS_R_FAR), "W-0 R": an.sample("W-0", OBS_R_FAR)}
    if w_n_0:
        s.update({"W-n-0 NR": an.sample("W-n-0", OBS_NR_FAR),
                  "W-n-0 R": an.sample("W-n-0", OBS_R_FAR)})
    pt = {k: v.point() for k, v in s.items()}
    bt = {k: v.boot(idx) for k, v in s.items()}
    out = {"cells": {k: rate(v) for k, v in s.items()}}
    pen_nr, pen_r = _diff(pt["F-0 NR"], pt["W-0 NR"]), _diff(pt["F-0 R"], pt["W-0 R"])
    delta = _diff(pen_nr, pen_r)
    d_nr, d_r = bt["F-0 NR"] - bt["W-0 NR"], bt["F-0 R"] - bt["W-0 R"]
    d_delta = d_nr - d_r
    out["penalty_nr"] = summarise(pen_nr, d_nr)
    out["penalty_r"] = summarise(pen_r, d_r)
    out["delta_h1"] = summarise(delta, d_delta)
    out["computable"] = delta is not None
    out["p_one_sided"] = p_null_le(d_delta, 0.0) if delta is not None else None
    up90 = (out["delta_h1"]["ci90"] or [None, None])[1]
    out["kill"] = (h1_kill(delta, up90) if delta is not None and up90 is not None else None)
    out["manipulation_check"] = None if pen_nr is None else manipulation_met(pen_nr)
    out["recoverable_within_5pp"] = None if pen_r is None else recoverable_within(pen_r)
    mc = h1_model_check(glm, delta, firth=firth)
    sign = mc["sign"]
    st = standin.get("estimate")
    mc.update(standin_estimate=st, standin_agrees=st is not None and st > GLM_SIGN_EPS,
              standin_sign_disagrees=(st is not None and _has_sign(sign)
                                      and _has_sign(_sign(st)) and _sign(st) != sign))
    out["model_check"] = mc
    out["model_check_sensitivity"] = h1_rule_sensitivity(glm, delta, mc["rule"], firth)
    out["scales_disagree_in_sign"] =(delta is not None and delta != 0 and sign not in (None, 0)
                                      and (delta > 0) != (sign > 0))
    if not w_n_0:
        out["w_n_0_alongside"] = {"status": NOT_RUN_BUDGET,
                                  "note": "W-n-0 did not run (R8's size rule): no reading"}
        return out
    pn_nr, pn_r = (_diff(pt["F-0 NR"], pt["W-n-0 NR"]), _diff(pt["F-0 R"], pt["W-n-0 R"]))
    dn_nr, dn_r = bt["F-0 NR"] - bt["W-n-0 NR"], bt["F-0 R"] - bt["W-n-0 R"]
    out["w_n_0_alongside"] = {"penalty_nr": summarise(pn_nr, dn_nr),
                              "penalty_r": summarise(pn_r, dn_r),
                              "difference": summarise(_diff(pn_nr, pn_r), dn_nr - dn_r),
                              "note": "W-n-0 against F-0: the notes-rescue condition, "
                                      "reported alongside H1, not tested (§3 H1)"}
    return out


def lookups_reading(an: Analysis) -> dict:
    """§3 H1's lookups prediction, with its zero-lookup rule."""
    f, w = an.sample("F-0", OBS_R_FAR, "n_lookups"), an.sample("W-0", OBS_R_FAR, "n_lookups")
    mf, mw = f.point(), w.point()
    bf, bw = f.boot(an.idx), w.boot(an.idx)
    out = {"task_cell": OBS_R_FAR, "mean_F0": _f(mf), "mean_W0": _f(mw),
           "n_F0": f.count, "n_W0": w.count, "lookups_F0": int(f.total),
           "lookups_W0": int(w.total), "difference": summarise(_diff(mw, mf), bw - bf)}
    if mf is None or mw is None:
        out.update(ratio=None, met=None, rule="not computable: a cell has no episode")
    elif mf == 0:
        lo = (out["difference"]["ci90"] or [None])[0]
        out.update(ratio=None, met=lo is not None and lo > TOL,
                   rule="F-0 looked nothing up, so the ratio is undefined: met iff the lower "
                        "bound of the 90% CI of the difference (W-0 - F-0) is above 0")
    else:
        r = mw / mf
        out.update(ratio=summarise(r, _ratio_dist(bw, bf)), met=ratio_met(r),
                   rule="met iff mean lookups W-0 / F-0 >= 1.30 (point estimate)")
    return out


def token_ratios(an: Analysis) -> dict:
    """R_need (primary), R_tok and the literal ratio (§3 H1, D8)."""
    p = an.prim
    out = {}
    for name, value, mask in (("R_need", "need_tokens", p.need_complete.astype(bool)),
                              ("R_tok", "tokens_total", None)):
        s = {(h, d): an.sample(h, OBS_R[d], value, mask=mask)
             for h in ("F-0", "W-0") for d in ("near", "far")}
        pt = {k: v.point() for k, v in s.items()}
        bt = {k: v.boot(an.idx) for k, v in s.items()}
        far = _ratio(pt[("W-0", "far")], pt[("F-0", "far")])
        near = _ratio(pt[("W-0", "near")], pt[("F-0", "near")])
        r = _ratio(far, near)
        dist = _ratio_dist(_ratio_dist(bt[("W-0", "far")], bt[("F-0", "far")]),
                           _ratio_dist(bt[("W-0", "near")], bt[("F-0", "near")]))
        out[name] = {"means": {f"{h} {d}": _f(pt[(h, d)]) for h, d in s},
                     "n": {f"{h} {d}": s[(h, d)].count for h, d in s},
                     "ratio": summarise(r, dist),
                     "at_least_1_30": None if r is None else ratio_met(r)}
        if name == "R_tok":
            out["literal"] = {"ratio": summarise(far, _ratio_dist(bt[("W-0", "far")],
                                                                  bt[("F-0", "far")])),
                              "at_least_1_30": None if far is None else ratio_met(far)}
    sel = (p[(p.variant == BASE) & p.cell.isin(("F-0", "W-0"))
             & p.task_cell.isin(tuple(OBS_R.values()))])
    complete = sel.need_complete.astype(bool)
    out["R_need"]["episodes_left_out_need_phase_incomplete"] = int((~complete).sum())
    out["R_need"]["episodes_left_out_no_tokens"] = int(
        (complete & ~np.isfinite(sel.need_tokens.to_numpy(float))).sum())
    out["R_need"]["prediction_met"] = out["R_need"]["at_least_1_30"]
    return out


def h3_reading(an: Analysis, glm: dict, glm_ps: dict) -> dict:
    """§3 H3 on luna (above), with the per-cell differences. `glm` is §9.4's registered model
    (`h3_glm_literal`), which decides; `glm_ps` power_sim's (`h3_glm_powersim`), a sensitivity
    analysis."""
    st, f0 = an.sample(SINGLE_TURN, H3_CELLS), an.sample("F-0", H3_CELLS)
    d = _diff(st.point(), f0.point())
    dist = st.boot(an.idx) - f0.boot(an.idx)
    out = {"cells": {"single-turn": rate(st), "F-0": rate(f0)}, "delta_h3": summarise(d, dist),
           "computable": d is not None,
           "p_one_sided": p_null_ge(dist, float(H3_MARGIN)) if d is not None else None}
    lo90, up90 = out["delta_h3"]["ci90"] or [None, None]
    out["prediction_holds"] = None if up90 is None else h3_holds(up90)
    out["ci90_above_margin"] = None if lo90 is None else lo90 > float(H3_MARGIN) + TOL
    out["per_cell"] = {}
    for tc in H3_CELLS:
        a, b = an.sample(SINGLE_TURN, tc), an.sample("F-0", tc)
        out["per_cell"][tc] = {"single-turn": rate(a), "F-0": rate(b),
                               "difference": summarise(_diff(a.point(), b.point()),
                                                       a.boot(an.idx) - b.boot(an.idx))}
    ame, est, status = glm.get("ame"), glm.get("estimate"), glm.get("logit_status", FINITE)
    sign = logit_sign(glm)
    agrees = ame is not None and ame < float(H3_MARGIN)
    ps_ame = glm_ps.get("ame")
    ps_agrees = ps_ame is not None and ps_ame < float(H3_MARGIN)
    out["model_check"] = {
        "model": glm.get("model"), "ame": ame, "agrees": agrees,
        "ame_informative": glm.get("ame_informative"),
        "n_pairs": glm.get("n_pairs"), "n_pairs_informative": glm.get("n_pairs_informative"),
        "arm_logit": est, "arm_logit_status": status, "arm_logit_sign": sign,
        "arm_logit_ci90": glm.get("ci90"), "arm_logit_ci95": glm.get("ci95"),
        "arm_no_variation": glm.get("arm_no_variation") or [],
        "powersim_model": glm_ps.get("model"), "powersim_ame": ps_ame,
        "powersim_agrees": ps_agrees,
        "powersim_disagrees": ame is not None and ps_ame is not None and ps_agrees != agrees}
    out["scales_disagree_in_sign"] = (d is not None and d != 0 and sign not in (None, 0)
                                      and (d > 0) != (sign > 0))
    return out


def family_readings(h1: dict, h3: dict) -> dict:
    """Holm over the family of 2 (R6 change 9) and the family-of-4 sensitivity; "supported"
    (§9.4, D26); the verdicts (reading 16)."""
    p1, p3 = h1["p_one_sided"], h3["p_one_sided"]
    two = holm([p1, p3])
    four = holm([p1, p3] + [1.0] * H2_TESTS_NOT_RUN)
    m1, m3 = h1["model_check"]["agrees"], h3["model_check"]["agrees"]
    out = {"family_of_2": {**two, "tests": ["H1", "H3"]},
           "family_of_4_sensitivity": {**four, "tests": ["H1", "H3", "H2 success (not run)",
                                                         "H2 tokens (not run)"]},
           "unadjusted": {"H1": p1 is not None and p1 <= ALPHA,
                          "H3": p3 is not None and p3 <= ALPHA}}
    out["H1"] = {"holm_rejects": two["reject"][0], "model_agrees": m1,
                 "supported": bool(p1 is not None and two["reject"][0] and m1),
                 "supported_family_of_4": bool(p1 is not None and four["reject"][0] and m1)}
    out["H3"] = {"holm_rejects": two["reject"][1], "model_agrees": m3,
                 "supported": bool(p3 is not None and two["reject"][1] and m3),
                 "supported_family_of_4": bool(p3 is not None and four["reject"][1] and m3)}
    out["H1"]["verdict"] = h1_verdict(out["H1"]["supported"], bool(h1.get("kill")),
                                      bool(p1 is not None and two["reject"][0]))
    out["H1"]["sensitivity_rules"] = {}                  # the rules not in force (ruled item 1)
    for rule, s in (h1.get("model_check_sensitivity") or {}).items():
        sup = bool(p1 is not None and two["reject"][0] and s["agrees"])
        out["H1"]["sensitivity_rules"][rule] = {
            "model_agrees": s["agrees"], "supported": sup,
            "verdict": h1_verdict(sup, bool(h1.get("kill")),
                                  bool(p1 is not None and two["reject"][0]))}
    lo90 = ((h3.get("delta_h3") or {}).get("ci90") or [None])[0]
    out["H3"]["verdict"] = h3_verdict(out["H3"]["supported"], lo90,
                                      bool(p3 is not None and two["reject"][1]))
    return out


def replication_label(p: float | None, agrees: bool) -> str:
    """A replication test's label (R8): whether its unadjusted one-sided test rejects at 0.05
    and whether its model check agrees, with no confirmatory word."""
    if p is None:
        return "not computable: a cell has no episode"
    test = ("the unadjusted test rejects" if p <= ALPHA
            else "the unadjusted test does not reject")
    return f"{test}, and the model check {'agrees' if agrees else 'does not agree'}"


H3_AGAINST = "the whole 90% CI of Δ_H3 lies above 5pp, against the prediction"


def replication_readings(h1: dict, h3: dict) -> dict:
    """R8's readings of the replication's tests (PREREG §17.8, Status in the analysis): outside
    luna's Holm family, each test's unadjusted one-sided bootstrap p-value at 0.05 and its model
    check, as `replication_label`; H1's kill reading as on luna, which reads luna only; the H1
    rules not in force (ruled item 1) as sensitivity lines, which enter no reading."""
    p1, p3 = h1["p_one_sided"], h3["p_one_sided"]
    m1, m3 = bool(h1["model_check"]["agrees"]), bool(h3["model_check"]["agrees"])
    lo90 = ((h3.get("delta_h3") or {}).get("ci90") or [None])[0]
    against = lo90 is not None and lo90 > float(H3_MARGIN) + TOL
    out = {"alpha_one_sided": ALPHA,
           "holm": "outside luna's Holm family (R8; R6 change 9): unadjusted p-values only",
           "H1": {"test": "H0: Δ_H1 ≤ 0", "p_one_sided": p1,
                  "rejects_unadjusted": p1 is not None and p1 <= ALPHA, "model_agrees": m1,
                  "label": replication_label(p1, m1), "kill_reading": h1.get("kill"),
                  "kill_note": ("H1's kill rule reads luna only (R8): this reading neither "
                                "kills nor confirms H1")},
           "H3": {"test": "H0: Δ_H3 ≥ 5pp", "p_one_sided": p3,
                  "rejects_unadjusted": p3 is not None and p3 <= ALPHA, "model_agrees": m3,
                  "label": replication_label(p3, m3) + (f"; {H3_AGAINST}" if against else ""),
                  "ci90_above_margin": against}}
    out["H1"]["sensitivity_rules"] = {
        rule: {"model_agrees": s["agrees"], "label": replication_label(p1, bool(s["agrees"]))}
        for rule, s in (h1.get("model_check_sensitivity") or {}).items()}
    return out


def h1_predictions(h1: dict, lookups: dict, tok: dict) -> dict:
    """PLAN §4's H1 predictions, each on its point estimate (§3 H1)."""
    parts = {"non-recoverable drop >= 25pp (manipulation check)": h1["manipulation_check"],
             "recoverable within 5pp": h1["recoverable_within_5pp"],
             "lookups rise >= 30%": lookups["met"],
             "need-phase tokens rise >= 30% (R_need)": tok["R_need"]["prediction_met"]}
    return {"parts": parts, "all_met": all(v is True for v in parts.values())}


# --- §2.8 accounting by cell ----------------------------------------------------------------

def s_planned(cell: str, distance: str) -> int | None:
    """S_planned of §2.8: 1 in F cells; window 1 near, 0 far; summary 0 far, unset near."""
    history = CELLS[cell].history
    if history == "full":
        return 1
    if history == "window":
        return int(distance == "near")
    return 0 if distance == "far" else None


def _rate(df: pd.DataFrame) -> dict:
    n = len(df)
    k = int(df["success"].sum()) if n else 0
    return {"n": n, "successes": k, "rate": k / n if n else None}


def accounting(prim: pd.DataFrame, cells: tuple[str, ...] = HARNESS_CELLS) -> list[dict]:
    """§2.8 and §9.6 per harness cell of `cells` x task cell (base, repeat 0)."""
    rows = []
    for cell in cells:
        for tc in TASK_CELLS:
            sub = prim[(prim.cell == cell) & (prim.variant == BASE) & (prim.task_cell == tc)]
            dist = TaskCell.from_id(tc).distance
            planned = s_planned(cell, dist)
            sv = sub.s_verbatim
            lost = sub[sv == 0]
            row = {"cell": cell, "task_cell": tc, "n": len(sub), "S_planned": planned,
                   "S_verbatim_1": int((sv == 1).sum()), "S_verbatim_0": int((sv == 0).sum()),
                   "S_verbatim_unknown": int(sv.isna().sum()),
                   "S_1": int((sub.s_any == 1).sum()),
                   "planned_vs_verbatim_mismatch": (None if planned is None else
                                                    int(((sv != planned) & sv.notna()).sum())),
                   "near_losses": (int((sv == 0).sum()) if planned == 1 and dist == "near"
                                   and cell in WINDOW_CELLS else None),
                   "residual_at_S1": _rate(sub[sv == 1]),
                   "success_given_S0": _rate(lost),
                   "rescued_with_lookup": None, "rescued_without_lookup": None,
                   "P_carried": None, "used_given_carried": None,
                   "exploratory": cell in SUMMARY_CELLS}
            if row["near_losses"] is not None:
                row["near_loss_share"] = row["near_losses"] / len(sub) if len(sub) else None
            if cell in CARRY_CELLS:
                carried = lost[lost.s_carried == 1]
                not_carried = lost[lost.s_carried == 0]
                row["P_carried"] = {"n": len(lost), "carried": len(carried),
                                    "rate": len(carried) / len(lost) if len(lost) else None}
                row["used_given_carried"] = _rate(carried)
                pool = not_carried
            else:
                pool = lost
            row["rescued_with_lookup"] = _rate(pool[pool.n_lookups >= 1])
            row["rescued_without_lookup"] = _rate(pool[pool.n_lookups == 0])
            if cell in SUMMARY_CELLS:
                label = sub.compacted_between.map(
                    lambda v: "none" if pd.isna(v) else str(int(v)))
                row["by_compacted_between"] = {
                    str(k): {"n": len(g), "S_verbatim_1": int((g.s_verbatim == 1).sum()),
                             "S_1": int((g.s_any == 1).sum()), "success": _rate(g)}
                    for k, g in sub.groupby(label, sort=True)}
            rows.append(row)
    return rows


# --- cells, exclusions, repeats, model strings ----------------------------------------------

def cell_table(prim: pd.DataFrame, kinds: tuple = KINDS, stopped: bool = False) -> list[dict]:
    """Each run kind's success per task cell, with its content failures. With `stopped` (Haiku,
    R8: refusals are counted per cell, with their category), also the step responses that
    stopped short, by reason (``refusal:<category>``, ``max_output_tokens``, ...)."""
    rows = []
    for cell, variant in kinds:
        for tc in (NR_TASK_CELLS if cell == SINGLE_TURN else TASK_CELLS):
            sub = prim[(prim.cell == cell) & (prim.variant == variant) & (prim.task_cell == tc)]
            outcomes = Counter(str(x) for x in sub.need_outcome)
            rows.append({"kind": kind_label(cell, variant), "cell": cell, "variant": variant,
                         "task_cell": tc, **_rate(sub),
                         "content_failures": {k: v for k, v in sorted(outcomes.items())
                                              if k not in ("correct", "wrong")},
                         "exploratory": cell in SUMMARY_CELLS})
            if stopped:
                reasons = Counter(x for t in sub.stopped for x in t)
                rows[-1]["stopped_responses"] = dict(sorted(reasons.items()))
                rows[-1]["episodes_with_a_refusal"] = int(sum(
                    any(x.startswith("refusal:") for x in t) for t in sub.stopped))
    return rows


def exclusion_table(resolved: dict, templates: int, kinds: tuple = KINDS,
                    echo: bool = True) -> list[dict]:
    """Per run kind and task cell, over the repeat-0 keys of templates 0..T-1: keys with a
    record, keys never played, exclusions by reason (echo, transport, no final record in a
    closed sweep), pending keys and dropped duplicates (§13: counts per cell). With `echo`
    False (Haiku, R8: no echo) a record-holding exclusion is the runner's own mark,
    ``excluded_by_runner``, with no echo share."""
    rows = []
    for cell, variant in kinds:
        for tc in (NR_TASK_CELLS if cell == SINGLE_TURN else TASK_CELLS):
            c: Counter = Counter()
            for t in range(templates):
                r = resolved.get((cell, episode_id_of(cell, variant, t, tc), 0))
                if r is None:
                    c["never_played"] += 1
                    continue
                c["keys"] += 1
                c["dropped_duplicates"] += len(r.dropped)
                if r.status == "pending":
                    c["pending"] += 1
                elif r.closed:
                    c["excluded_no_final"] += 1
                elif r.status == "excluded":
                    c["excluded_echo" if r.record is not None else "excluded_transport"] += 1
            share = c["excluded_echo"] / c["keys"] if c["keys"] else 0.0
            excluded = ({"excluded_echo": c["excluded_echo"]} if echo
                        else {"excluded_by_runner": c["excluded_echo"]})
            rows.append({"kind": kind_label(cell, variant), "cell": cell, "variant": variant,
                         "task_cell": tc, "keys": c["keys"], "never_played": c["never_played"],
                         **excluded,
                         "excluded_transport": c["excluded_transport"],
                         "excluded_no_final": c["excluded_no_final"], "pending": c["pending"],
                         "dropped_duplicates": c["dropped_duplicates"],
                         **({"echo_share": share, "echo_over_5pct": share > ECHO_SHARE_MAX}
                            if echo else {})})
    return rows


def repeat_agreement(table: pd.DataFrame, templates: int, kinds: tuple = KINDS) -> list[dict]:
    """§2.9: within-template noise, as the agreement between the two plays of each episode."""
    ok = table[(table.status == "counted") & (table.template < templates)]
    rows = []
    for cell, variant in kinds:
        sub = ok[(ok.cell == cell) & (ok.variant == variant)]
        r0 = sub[sub.repeat == 0].set_index("episode_id")["success"]
        r1 = sub[sub.repeat == 1].set_index("episode_id")["success"]
        both = r0.index.intersection(r1.index)
        a, b = r0.loc[both].to_numpy(), r1.loc[both].to_numpy()
        rows.append({"kind": kind_label(cell, variant), "pairs": len(both),
                     "agree": int((a == b).sum()),
                     "agreement": float((a == b).mean()) if len(both) else None,
                     "repeat0_only_success": int(((a == 1) & (b == 0)).sum()),
                     "repeat1_only_success": int(((a == 0) & (b == 1)).sum()),
                     "repeat1_records": int((sub.repeat == 1).sum())})
    return rows


MIXED = "more than one string"


def deltas(an: Analysis) -> dict:
    """Delta_H1 and Delta_H3 with their bootstrap intervals, on `an`'s episodes."""
    s = {k: an.sample(c, tc) for k, (c, tc) in {
        "f_nr": ("F-0", OBS_NR_FAR), "w_nr": ("W-0", OBS_NR_FAR), "f_r": ("F-0", OBS_R_FAR),
        "w_r": ("W-0", OBS_R_FAR), "st": (SINGLE_TURN, H3_CELLS), "f3": ("F-0", H3_CELLS)}.items()}
    pt = {k: v.point() for k, v in s.items()}
    bt = {k: v.boot(an.idx) for k, v in s.items()}
    d1 = _diff(_diff(pt["f_nr"], pt["w_nr"]), _diff(pt["f_r"], pt["w_r"]))
    return {"delta_h1": summarise(d1, (bt["f_nr"] - bt["w_nr"]) - (bt["f_r"] - bt["w_r"])),
            "delta_h3": summarise(_diff(pt["st"], pt["f3"]), bt["st"] - bt["f3"])}


def model_strings(an: Analysis) -> dict:
    """§6: the returned model strings; if more than one, Delta_H1 and Delta_H3 per group of
    records, with bootstrap intervals on the same resamples (reading 12): one group per single
    string, one for the records whose responses came from more than one string."""
    counts = Counter(an.prim.models)
    out = {"strings": dict(counts), "split": None,
           "records_with_more_than_one_string": int(sum(v for k, v in counts.items()
                                                        if "|" in k))}
    if len(counts) <= 1:
        return out
    group = an.prim.models.map(lambda m: MIXED if "|" in m else (m or "none"))
    split = {}
    for g in sorted(set(group)):
        sub = Analysis(an.prim[group == g], an.templates, an.idx)
        split[g] = {"episodes": int((group == g).sum()), **deltas(sub)}
    out["split"] = split
    return out


def achieved_power(path: Path = POWER_DECISION) -> list[dict] | None:
    """The achieved power at the worst Holm step quoted with the results (§9.4), from the
    committed luna power run, with each scenario's F-0 level (power_sim's `LunaSetup`)."""
    if not path.is_file():
        return None
    setups = {s.name: s for s in (ps.LUNA_PRIMARY, ps.LUNA_PESSIMISTIC)}
    with open(path, encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("reading") == POWER_READING]
    return [{"scenario": r["scenario"], "T_set": int(r["T_set"]),
             "power_h1": float(r["power_h1_at_T_set"]), "power_h3": float(r["power_h3_at_T_set"]),
             "p_f0_observed_far": (setups[r["scenario"]].p_f0_obs if r["scenario"] in setups
                                   else None),
             "source": _rel(path)} for r in rows]


def replication_power(path: Path | None, templates: int) -> dict:
    """The replication's power at its T (R8: simulated with `analysis.power_sim` from Haiku's
    validity runs, at one-sided 0.05, reported, not used to set T): from a per-T power table of
    power_sim's luna part (``luna_power.csv``), the rows at T. P(the unadjusted test rejects)
    is ``P_h*_unadjusted``; P(it rejects and power_sim's model check agrees) is that minus
    ``P_h*_glm_veto`` (it rejects and the check does not agree). Unavailable without a table
    or a row at T."""
    out = {"available": False, "T": templates, "alpha_one_sided": ALPHA,
           "source": None if path is None else _rel(path), "rows": []}
    if path is None:
        out["note"] = "no power table given (--power-path)"
        return out
    if not Path(path).is_file():
        out["note"] = f"no power table at {path}"
        return out
    with open(path, encoding="utf-8", newline="") as fh:
        table = list(csv.DictReader(fh))
    missing = [c for c in POWER_TABLE_COLUMNS if table and c not in table[0]]
    if not table or missing:
        out["note"] = ("not a per-T power table of power_sim's luna part (luna_power.csv): "
                       + (f"no column {', '.join(missing)}" if missing else "no rows"))
        return out
    for r in table:
        if int(r["templates"]) != templates:
            continue
        row = {"scenario": r["scenario"], "templates": templates}
        for h in ("h1", "h3"):
            rejects, veto = float(r[f"P_{h}_unadjusted"]), float(r[f"P_{h}_glm_veto"])
            row[f"power_{h}_rejects"] = rejects
            row[f"power_{h}_rejects_and_model_agrees"] = rejects - veto
        for k in ("reps", "p_f0_onr", "p_f0_or", "true_delta_h1_pp", "true_delta_h3_pp"):
            if r.get(k) not in (None, ""):
                row[k] = float(r[k])
        out["rows"].append(row)
    if out["rows"]:
        out["available"] = True
    else:
        out["note"] = f"the power table has no row at T = {templates}"
    return out


def bayesian_glmm(prim: pd.DataFrame, seed: int, settings: dict | None = None) -> dict:
    """§9.1's sensitivity model (above): a Bayesian logistic GLMM with template random
    intercepts, fitted by bambi on the §9.1 GLM's rows; the posterior of its W-0 x R
    coefficient. It enters no decision; a failure is reported, not raised."""
    settings = dict(settings or BAYES_SETTINGS)
    sub = prim[(prim.variant == BASE) & prim.cell.isin(("F-0", "W-0"))]
    df = pd.DataFrame({"success": sub["success"].to_numpy(int),
                       "W": (sub.cell == "W-0").to_numpy(int),
                       "R": sub.recoverable.to_numpy(bool).astype(int),
                       "D": (sub.fact == "derived").to_numpy(int),
                       "N": (sub.distance == "near").to_numpy(int),
                       "template": [f"t{t}" for t in sub["template"]]})
    out = {"status": "not run", "model": BAYES_FORMULA, "family": "bernoulli",
           "priors": "bambi's defaults", "target": "W:R", "seed": seed, **settings,
           "n_rows": len(df), "n_templates": int(df.template.nunique())}
    if df.empty or df.success.nunique() < 2:
        out["note"] = "no outcome variation in the rows: no fit"
        return out
    try:
        import arviz as az
        import bambi as bmb
    except ImportError as e:
        out["note"] = f"bambi is not installed ({e}): run uv sync"
        return out
    out["versions"] = {p: importlib.metadata.version(p) for p in ("bambi", "pymc", "arviz")}
    quiet = [logging.getLogger(n) for n in ("pymc", "bambi", "pytensor")]
    levels = [lg.level for lg in quiet]
    try:
        for lg in quiet:
            lg.setLevel(logging.ERROR)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = bmb.Model(BAYES_FORMULA, df, family="bernoulli")
            idata = model.fit(draws=settings["draws"], tune=settings["tune"],
                              chains=settings["chains"], cores=1, random_seed=seed,
                              progressbar=False)
            post = idata.posterior
            draws = np.asarray(post["W:R"].values, float)
            rhat = float(az.rhat(post["W:R"]))
            ess = float(az.ess(post["W:R"]))
            rhat_max = max(float(np.nanmax(np.asarray(az.rhat(post[v]), float)))
                           for v in post.data_vars)
            divergences = int(np.asarray(idata.sample_stats["diverging"]).sum())
    except Exception as e:  # noqa: BLE001 - a sensitivity fit's failure is reported
        out.update(status="failed", note=f"{type(e).__name__}: {e}")
        return out
    finally:
        for lg, lv in zip(quiet, levels, strict=True):
            lg.setLevel(lv)
    flat = draws.ravel()
    out.update(status="fitted", median=float(np.median(flat)), mean=float(flat.mean()),
               ci90=[float(x) for x in np.quantile(flat, [0.05, 0.95])],
               ci95=[float(x) for x in np.quantile(flat, [0.025, 0.975])],
               p_positive=float(np.mean(flat > 0)), rhat=rhat, ess_bulk=ess,
               rhat_max_all=rhat_max, divergences=divergences, converged=rhat_max <= RHAT_MAX)
    return out


# --- compute -------------------------------------------------------------------------------

def _rel(p: Path) -> str:
    p = Path(p).resolve()
    return p.relative_to(REPO_ROOT).as_posix() if p.is_relative_to(REPO_ROOT) else str(p)


def run_row(run: Run, resolved: dict) -> dict:
    counted = sum(1 for r in resolved.values() if r.run_id == run.run_id)
    return {"run_id": run.run_id, "cell": run.cell, "variants": list(run.variants),
            "repeat_index": run.repeat_index, "started_utc": run.started.isoformat(),
            "exit_reason": run.exit_reason, "records": len(run.records),
            "records_counted": counted, "model_returned": run.model_returned}


def _public(d: dict) -> dict:
    """A GLM's output without its private keys (the template intercepts)."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def compute(root: Path, generated: str, git: dict, *, boot: int = N_BOOT,
            allow_incomplete: bool = False, raw_root: Path | None = None,
            links: dict[str, str] | None = None, templates: int | None = None,
            power_path: Path | None = None, runs: list[str] | None = None,
            sweep_closed: str | None = None, bayes: bool = True, model: str | None = None,
            experiment: str | None = None) -> dict:
    """H1 and H3 from the files under `root`. Raises Refusal (incomplete without
    `allow_incomplete`, undeclared duplicates, inconsistent records, a `runs` entry not found)
    or AccountingBug. `model` is the model whose runs are read (`profile`: luna's by default;
    claude-haiku-5-5 for R8's replication), in `experiment` (default its registered one; any
    other is PROVISIONAL). `templates` defaults to the model's T (`registered.LUNA_T`,
    `registered.HAIKU_T`), read at call time. `runs` is the --run input list (None: every run
    of the model found, PROVISIONAL); `sweep_closed` the decisions.md entry that closed the
    sweep (--sweep-closed); `bayes` False skips the Bayesian sensitivity fit (PROVISIONAL);
    `power_path` the power file (luna: its committed power run; Haiku: none unless given)."""
    prof = profile(model, experiment)
    templates = templates or prof.T
    power_path = power_path or prof.power_path
    raw_root = raw_root or root / "raw"
    links = dict(links or {})
    if sweep_closed is not None and not sweep_closed.strip():
        raise Refusal("--sweep-closed needs the results/decisions.md entry that closed the sweep")
    seed, draw_path = read_seed(root)
    found, skipped = discover(root, runs, prof)
    if not found:
        raise Refusal(f"no {prof.model} run of experiment {prof.experiment} on the default "
                      f"config under {root}")
    resolved, warn = resolve(found, links, sweep_closed=sweep_closed is not None,
                             echo=prof.echo)
    incomplete, deviations = completeness(resolved, templates, sweep_closed is not None,
                                          prof.kinds)
    if incomplete and not allow_incomplete:
        raise Refusal("the repeat-0 sweep is incomplete:\n" + "\n".join(
            f"  - {x}" for x in incomplete) + "\nWait for the runs (a transport failure needs "
            "its §13 re-run), close the sweep with --sweep-closed REF if the researcher has "
            "closed it, or pass --allow-incomplete to see what exists (PROVISIONAL).")
    check = accounting_check(found, raw_root, prof.experiment, prof.api)
    if check["bugs"]:
        raise AccountingBug(
            "PREREG §2.8's bug stop: window-accounting bug(s), so no result is reported until "
            "they are found:\n" + "\n".join(f"  - {b}" for b in check["bugs"]))
    if check["missing_transcripts"]:
        incomplete.append("no raw transcript for window-cell run(s) "
                          + ", ".join(check["missing_transcripts"])
                          + f" under {raw_root}: §2.8's replay cannot be made")
        if not allow_incomplete:
            raise Refusal(incomplete[-1] + "\nRun it in the checkout that holds results/raw/, "
                          "pass --raw-root, or pass --allow-incomplete (PROVISIONAL).")
    table, warn_rows = episode_table(resolved)
    warn += warn_rows + check["warnings"]
    beyond = sorted({int(t) for t in table.template if t >= templates}) if len(table) else []
    if beyond:
        warn.append(f"records on templates {beyond[0]}..{beyond[-1]} lie outside 0..{templates - 1}"
                    " and are left out")
    if any(s["reason"].endswith("not in the input list (--run)") for s in skipped):
        warn.append(f"{prof.name} sweep run(s) found but not in the input list (--run): see "
                    "Checks")
    stopped = sorted(r.run_id for r in found if r.exit_reason == REQUEST_CHECK_STOP)
    if stopped:
        warn.append(f"run(s) stopped by the request-side check ({REQUEST_CHECK_STOP}): "
                    + ", ".join(stopped) + ". A harness bug (R8): the episode it stopped at is "
                    "excluded, and no record of it was written")
    provisional = list(incomplete)
    if prof.experiment != prof.registered_experiment:
        provisional.append(f"--experiment {prof.experiment}: not {prof.name}'s registered "
                           f"experiment ({prof.registered_experiment})")
    if runs is None:
        provisional.append("no input list: the runs read were found, not named with --run "
                           "(harnesses/DESIGN.md §7.8)")
    if boot != N_BOOT:
        provisional.append(f"--boot {boot}: not the registered 10,000 resamples")
    if not bayes:
        provisional.append("--no-bayes: §9.1's Bayesian sensitivity model was not fitted")
    prim = table[(table.repeat == 0) & (table.status == "counted")
                 & (table.template < templates)].reset_index(drop=True)
    idx = resample_indices(templates, seed + BOOT_SEED_OFFSET, boot)
    an = Analysis(prim, templates, idx)
    w_n_0 = "W-n-0" in prof.cells
    glm = glm_91(prim)
    glm_wn = glm_91(prim, ("W-0", "W-n-0")) if w_n_0 else None
    standin = h1_standin(prim)
    # the Firth fit, whenever the logit-scale Delta_H1 is not finite: read by the rule in force
    # ("firth") or, were another rule in force, by its sensitivity line
    firth = glm_91_firth(prim) if glm.get("logit_status") != FINITE else None
    h1 = h1_reading(an, glm, standin, firth, w_n_0=w_n_0)
    lookups = lookups_reading(an)
    tok = token_ratios(an)
    if tok["R_need"]["episodes_left_out_no_tokens"]:
        warn.append(f"{tok['R_need']['episodes_left_out_no_tokens']} observed-R F-0/W-0 "
                    "episode(s) have a complete need phase without need_phase.tokens: left out "
                    "of R_need")
    glm3, glm3_ps = h3_glm_literal(prim), h3_glm_powersim(prim)
    h3 = h3_reading(an, glm3, glm3_ps)
    rep = prof.replication
    fam = replication_readings(h1, h3) if rep else family_readings(h1, h3)
    status = PROVISIONAL if provisional else FINAL
    excl = exclusion_table(resolved, templates, prof.kinds, prof.echo)
    bayes_out = (bayesian_glmm(prim, seed + BAYES_SEED_OFFSET) if bayes else
                 {"status": "not run", "note": "--no-bayes"})
    model_sign = h1["model_check"]["sign"]
    if bayes_out.get("status") == "fitted":
        bayes_out["sign_disagrees_with_glm"] = (_has_sign(model_sign)
                                                and _has_sign(_sign(bayes_out["median"]))
                                                and _sign(bayes_out["median"]) != model_sign)
    # luna's output keeps exactly the keys, in the order, of its cited output
    # (LUNA_CITED_OUTPUT); the replication's differ where R8 does (profile, labels, power)
    out = {
        "generated_utc": generated, **git, "prereg_version": runmeta.prereg_version(),
        "status": status, "provisional_reasons": provisional, "deviations": deviations,
        "sweep_closed": sweep_closed, "warnings": warn,
        "inputs": {"results_root": _rel(root), "raw_root": _rel(raw_root),
                   "draw_json": _rel(draw_path),
                   "input_list": None if runs is None else list(runs),
                   "runs": [run_row(r, resolved) for r in sorted(found,
                                                                 key=lambda x: x.started)],
                   "rerun_links": links, "skipped": skipped},
        **({"profile": prof.public()} if rep else {}),
        "model": prof.model, "generator_config_hash": prof.generator_hash,
        "templates": templates,
        "seed": seed, "bootstrap": {"seed": seed + BOOT_SEED_OFFSET, "resamples": boot,
                                    "method": "percentile", "levels": list(LEVELS)},
        "h1_separation_rule": H1_SEPARATION_RULE,
        **({"pre_specified": list(PRE_SPECIFIED)} if rep
           else {"changed_after_final": list(CHANGED_AFTER_FINAL)}),
        "primary_episodes": len(prim),
        "accounting_check": {k: v for k, v in check.items() if k != "bugs"},
        "h1": h1, "h1_lookups": lookups, "h1_tokens": tok,
        "h1_predictions": h1_predictions(h1, lookups, tok), "h3": h3,
        **({"replication": fam} if rep else {"family": fam}),
        "glm_9_1": _public(glm),
        "glm_9_1_with_w_n_0": (_public(glm_wn) if glm_wn is not None
                               else {"status": NOT_RUN_BUDGET, "note": "W-n-0 did not run"}),
        "glm_9_1_firth": firth, "glm_h1_standin": standin,
        "glm_h3": _public(glm3), "glm_h3_powersim": glm3_ps,
        "bayesian_glmm": bayes_out,
        **({"power": replication_power(power_path, templates)} if rep
           else {"achieved_power": achieved_power(power_path)}),
        "accounting": accounting(prim, prof.cells),
        "cost_outcomes": cost_outcomes(prim, prof.cells),
        "cells": cell_table(prim, prof.kinds, stopped=not prof.echo), "exclusions": excl,
        **({"echo_cells_over_5pct": [f"{e['kind']} {e['task_cell']}" for e in excl
                                     if e["echo_over_5pct"]]} if prof.echo else {}),
        "repeats": repeat_agreement(table, templates, prof.kinds),
        "model_strings": model_strings(an),
        "dropped_records": [{"cell": r.key[0], "episode_id": r.key[1], "repeat": r.key[2],
                             "kept_from": r.run_id, "dropped": r.dropped}
                            for r in resolved.values() if r.dropped],
    }
    if glm_wn is not None:
        wn = logit_sign(glm_wn)
        out["glm_9_1_with_w_n_0"]["sign"] = wn
        out["glm_9_1_with_w_n_0"]["sign_disagrees"] = (wn not in (None, 0)
                                                       and model_sign not in (None, 0)
                                                       and wn != model_sign)
    return out


# --- summary -------------------------------------------------------------------------------

def _pp(x, digits: int = 1, sign: bool = True) -> str:
    if x is None:
        return "n/a"
    return f"{100 * x:+.{digits}f}pp" if sign else f"{100 * x:.{digits}f}pp"


def _ci(c: dict, key: str = "ci90", digits: int = 1) -> str:
    iv = c.get(key)
    return "n/a" if iv is None else f"[{_pp(iv[0], digits)}, {_pp(iv[1], digits)}]"


def _num_s(x, digits: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def _rate_s(r: dict) -> str:
    return "n/a" if not r or r.get("rate") is None else \
        f"{r['rate']:.3f} ({r['successes']}/{r['n']})"


def _yes(x) -> str:
    return {True: "yes", False: "no"}.get(x, "n/a")


def _ratio_s(c: dict | None) -> str:
    if c is None or c.get("estimate") is None:
        return "n/a"
    iv = c.get("ci90")
    return f"{c['estimate']:.3f}" + ("" if iv is None else f" [{iv[0]:.3f}, {iv[1]:.3f}]")


def _word(x, yes: str, no: str) -> str:
    return yes if x else no if x is False else "n/a"


def _iv_s(iv) -> str:
    return "n/a" if iv is None else f"[{iv[0]:.3f}, {iv[1]:.3f}]"


def _logit_s(est, status: str = FINITE, wald: dict | None = None) -> str:
    """A logit-scale estimate: the value with its 90% Wald interval when finite, else its limit
    (+∞, −∞ or undefined) with the stopping point statsmodels returned, or "no fit"."""
    label = {PLUS_INF: "+∞", MINUS_INF: "−∞"}.get(status, "undefined (∞ − ∞)")
    if est is None:
        return "n/a" if status == FINITE else f"{label} (no fit)"
    if status == FINITE:
        iv = (wald or {}).get("ci90")
        return f"{est:.3f}" + ("" if iv is None else f" (90% CI {_iv_s(iv)})")
    return f"{label} (statsmodels stops at {est:.2f})"


def _same(disagrees: bool, what: str, comparable: bool = True) -> str:
    """Whether two estimates agree in sign; "no sign to compare" when either has none."""
    if not comparable:
        return f"no sign to compare with {what}"
    return f"**its sign differs from {what}**" if disagrees else f"the same sign as {what}"


def _has_sign(x) -> bool:
    return x not in (None, 0)


def _bayes_line(b: dict, model_sign: int | None) -> str:
    if b.get("status") != "fitted":
        return (f"- Bayesian GLMM sensitivity (§9.1): {b.get('status', 'not run')}"
                f" ({b.get('note') or 'no note'}).")
    same = _same(bool(b.get("sign_disagrees_with_glm")), "the model check",
                 _has_sign(model_sign) and _has_sign(_sign(b["median"])))
    conv = ("" if b["converged"] else
            f", **not converged** (an R-hat above {RHAT_MAX})")
    return ("- Bayesian GLMM sensitivity (§9.1; bambi, template random intercepts, every "
            f"template kept; not a decision): W-0 × R posterior median {b['median']:.3f}, 90% "
            f"interval {_iv_s(b['ci90'])}, P(> 0) = {b['p_positive']:.3f}; R-hat "
            f"{b['rhat']:.3f} (largest over the parameters {b['rhat_max_all']:.3f}){conv}, bulk "
            f"ESS {b['ess_bulk']:.0f}, {b.get('divergences', 'n/a')} divergent transitions "
            "after tuning; "
            f"{same}.")


def _rep(h: dict) -> bool:
    """Whether `h` is R8's replication: its output has a "replication" block, luna's a
    "family" one (and no "profile")."""
    return "replication" in h


def _cells_of(h: dict) -> tuple[str, ...]:
    """The harness cells the output read: the profile's, or luna's (its output names none)."""
    return tuple((h.get("profile") or {}).get("cells") or HARNESS_CELLS)


def _name_of(h: dict) -> str:
    return (h.get("profile") or {}).get("name") or "luna"


def _h1_lines(h: dict) -> list[str]:
    rep = _rep(h)
    h1, g = h["h1"], h["glm_9_1"]
    fam = h["replication"] if rep else h["family"]
    mc, c = h1["model_check"], h1["cells"]
    if rep:
        test1 = (f"Unadjusted at one-sided 0.05 (outside luna's Holm family, R8): "
                 f"{_word(fam['H1']['rejects_unadjusted'], 'rejects', 'does not reject')}.")
    else:
        test1 = (f"Holm (family of 2): "
                 f"{_word(fam['H1']['holm_rejects'], 'rejects', 'does not reject')}.")
    wn_nr, wn_r = (_rate_s(c[k]) if k in c else "not run" for k in ("W-n-0 NR", "W-n-0 R"))
    L = ["### H1: recoverability turns a success penalty into a cost penalty", "",
         "| Cell (observed, far) | F-0 | W-0 | W-n-0 (alongside) |", "|---|---|---|---|",
         (f"| not recoverable | {_rate_s(c['F-0 NR'])} | {_rate_s(c['W-0 NR'])} | "
          f"{wn_nr} |"),
         (f"| recoverable | {_rate_s(c['F-0 R'])} | {_rate_s(c['W-0 R'])} | "
          f"{wn_r} |"), "",
         "| Quantity (probability scale) | Estimate | 90% CI | 95% CI |", "|---|---|---|---|"]
    for name, key in (("Penalty_NR = p(F-0, NR) − p(W-0, NR)", "penalty_nr"),
                      ("Penalty_R = p(F-0, R) − p(W-0, R)", "penalty_r"),
                      ("**Δ_H1 = Penalty_NR − Penalty_R**", "delta_h1")):
        L.append(f"| {name} | {_pp(h1[key]['estimate'])} | {_ci(h1[key])} | "
                 f"{_ci(h1[key], 'ci95')} |")
    con = g.get("contrasts") or {}
    pen = {k: _logit_s((con.get(k) or {}).get("estimate"),
                       (con.get(k) or {}).get("logit_status", FINITE), con.get(k))
           for k in ("penalty_nr_logit", "penalty_r_logit")}
    L += ["",
          (f"- One-sided bootstrap test, H0: Δ_H1 ≤ 0: p = {_num_s(h1['p_one_sided'], 4)}. "
           f"{test1}"),
          ("- Model check (§9.4; the §9.1 GLM, fitted by statsmodels on F-0 and W-0 × 8 task "
           "cells; the logit-scale Δ_H1 is its W-0 × R coefficient): "
           f"{_logit_s(mc['estimate'], mc['logit_status'], g)}; agrees (> 0): "
           f"**{_yes(mc['agrees'])}**, read from {mc['basis']}. Templates without outcome "
           f"variation dropped from the GLM: {g.get('n_templates_dropped', 'n/a')}.")]
    fz = h.get("glm_9_1_firth") or {}
    if mc["logit_status"] != FINITE:
        ruling = ("the researcher's ruling of 2026-10-10, module docstring; pre-specified for "
                  "Haiku by R8" if rep else "the researcher's ruling of 2026-10-10, module "
                  "docstring")
        L.append("- **The logit-scale Δ_H1 is not finite:** among the GLM's templates, "
                 + "; ".join(mc["h1_cells_no_variation"]) + f". The rule in force is "
                 f"`{mc['rule']}` (`H1_SEPARATION_RULE`; {ruling}): " + {
                     "literal": ("the sign of the limit decides; −∞ (an interaction that flips "
                                 "sign between the scales near a ceiling, §9.3) and an "
                                 "undefined sign do not agree."),
                     "firth": (("a Firth-penalized fit of the same model decides: "
                                + (_num_s(fz["estimate"]) if fz.get("estimate") is not None
                                   else f"no estimate ({fz.get('note') or 'no note'})") + ".")
                               if mc["estimate"] is not None else
                               "the §9.1 GLM was not fitted, so no rule applies."),
                     "probability-scale": ("the model check is not applicable, and the "
                                           "probability-scale sign is read.")}[mc["rule"]])
        sens, parts = fam["H1"].get("sensitivity_rules") or {}, []
        for rule, s in sens.items():
            fe = (h1.get("model_check_sensitivity") or {}).get(rule, {}).get("firth_estimate")
            parts.append(f"rule `{rule}`"
                         + (f" (Firth's W-0 × R {_num_s(fe)})" if rule == "firth" else "")
                         + f": the model check would agree: {_yes(s['model_agrees'])}, and "
                         + (f"the replication's label would be: {s['label']}" if rep
                            else f"H1 would be: {s['verdict']}"))
        if parts:
            L.append("- Sensitivity lines (the rules not in force, ruling of 2026-10-10; they "
                     "enter no decision): " + "; ".join(parts) + ".")
    wn, route = h["glm_9_1_with_w_n_0"], g.get("emulation_route")
    emu = (f"{_num_s(g.get('estimate_emulated'))} "
           f"({_same(g.get('emulated_sign_disagrees'), 'statsmodels')})" if route == "newton"
           else f"{_num_s(g.get('estimate_emulated'))} (its Newton steps failed and it fell "
           "back to statsmodels, so it is no independent check)" if route == "statsmodels"
           else "n/a")
    st = mc["standin_estimate"]
    st_same = _same(mc["standin_sign_disagrees"], "the model check",
                    _has_sign(mc["sign"]) and st is not None and _has_sign(_sign(st)))
    if wn.get("status") == NOT_RUN_BUDGET:
        wn_s = (" W-n-0 as a third harness level (a sensitivity analysis, ruling of "
                f"2026-10-10): not fitted, W-n-0 being {NOT_RUN_BUDGET}.")
    else:
        wn_same = _same(wn.get("sign_disagrees"), "the model check",
                        _has_sign(wn.get("sign")) and _has_sign(mc["sign"]))
        wn_s = (" W-n-0 as a third harness level (a sensitivity analysis, ruling of "
                "2026-10-10), W-0 × R "
                + _logit_s(wn.get("estimate"), wn.get("logit_status", FINITE), wn)
                + f" ({wn_same}).")
    L += [(f"- Logit scale (§9.3): Penalty_NR {pen['penalty_nr_logit']}, Penalty_R "
           f"{pen['penalty_r_logit']}, Δ_H1 {_logit_s(mc['estimate'], mc['logit_status'], g)}."),
          (f"- Cross-checks (not decisions): power_sim's emulation of the same fit {emu}; "
           f"power_sim's stand-in (4 cells; W, R, W × R) {_num_s(mc['standin_estimate'])} "
           f"({st_same}); the §9.1 GLM with" + wn_s),
          _bayes_line(h["bayesian_glmm"], mc["sign"])]
    if rep:
        L += [(f"- **H1, replication (R8): {fam['H1']['label']}.** Outside luna's Holm family "
               "and with no confirmatory label (R8): it neither confirms nor kills H1, and luna "
               "stays primary."),
              ("- **Kill reading** (computed as on luna: Δ_H1 < 10pp and the 90% upper bound "
               f"< 15pp): **{_word(h1['kill'], 'fires', 'does not fire')}**. H1's kill rule "
               "reads luna only (R8), so on Haiku this reading neither kills nor confirms H1.")]
    else:
        L += [(f"- **H1: {fam['H1']['verdict']}.** Supported needs the Holm test and the model "
               f"check (§9.4): {_yes(fam['H1']['holm_rejects'])} and "
               f"{_yes(fam['H1']['model_agrees'])}."),
              ("- **Kill rule** (Δ_H1 < 10pp and the 90% upper bound < 15pp): "
               f"**{_word(h1['kill'], 'fires', 'does not fire')}**"
               + (': drop the "success vs cost" framing (§3 H1).' if h1["kill"] else "."))]
    if h1["scales_disagree_in_sign"]:
        L.append("- **The probability and logit scales disagree in sign** (§9.3).")
    if g.get("no_variation_cells"):
        L.append("- Cells with no outcome variation in the GLM (quasi-separation; their "
                 "coefficients are large and finite only by the stopping rule): "
                 + "; ".join(g["no_variation_cells"]) + ".")
    pr, lk, tk = h["h1_predictions"], h["h1_lookups"], h["h1_tokens"]
    lookups = (_ratio_s(lk["ratio"]) if lk.get("ratio") else
               (f"F-0 none; W-0 − F-0 {_num_s(lk['difference']['estimate'])} "
                f"{_iv_s(lk['difference']['ci90'])}"))
    L += ["", "H1's predictions (point estimates, §3 H1):", "",
          "| Prediction | Value | Met |", "|---|---|---|",
          (f"| Manipulation check: Penalty_NR ≥ 25pp | {_pp(h1['penalty_nr']['estimate'])} | "
           f"{_yes(h1['manipulation_check'])} |"),
          ("| Recoverable success: \\|Penalty_R\\| ≤ 5pp | "
           f"{_pp(h1['penalty_r']['estimate'])} | {_yes(h1['recoverable_within_5pp'])} |"),
          (f"| Lookups: mean W-0 / F-0 ≥ 1.30 (observed-far-R) | {lookups} | "
           f"{_yes(lk['met'])} |"),
          (f"| Need-phase tokens: R_need ≥ 1.30 | {_ratio_s(tk['R_need']['ratio'])} | "
           f"{_yes(tk['R_need']['prediction_met'])} |"), "",
          (f"All four met: **{_yes(pr['all_met'])}**. Lookups: F-0 {lk['lookups_F0']} in "
           f"{lk['n_F0']} episodes, W-0 {lk['lookups_W0']} in {lk['n_W0']}. Secondary token "
           f"readings: R_tok {_ratio_s(tk['R_tok']['ratio'])}; the literal ratio "
           f"T(W-0, far) / T(F-0, far) {_ratio_s(tk['literal']['ratio'])} (it cannot reach "
           "1.30 by design, D8). Intervals are 90%.")]
    left = (tk["R_need"]["episodes_left_out_need_phase_incomplete"]
            + tk["R_need"].get("episodes_left_out_no_tokens", 0))
    if left:
        L.append(f"R_need leaves out {left} episode(s) whose need phase is incomplete or has "
                 "no token count.")
    wn = h1["w_n_0_alongside"]
    if wn.get("status") == NOT_RUN_BUDGET:
        L += ["", f"W-n-0 alongside: {NOT_RUN_BUDGET} (R8's size rule)."]
    else:
        L += ["", (f"W-n-0 alongside (not tested): penalty against F-0, NR "
                   f"{_pp(wn['penalty_nr']['estimate'])} {_ci(wn['penalty_nr'])}, R "
                   f"{_pp(wn['penalty_r']['estimate'])} {_ci(wn['penalty_r'])}.")]
    return L


def _h3_lines(h: dict) -> list[str]:
    rep = _rep(h)
    h3 = h["h3"]
    fam = h["replication"] if rep else h["family"]
    mc3 = h3["model_check"]
    if rep:
        test3 = (f"Unadjusted at one-sided 0.05 (outside luna's Holm family, R8): "
                 f"{_word(fam['H3']['rejects_unadjusted'], 'rejects', 'does not reject')}.")
    else:
        test3 = (f"Holm (family of 2): "
                 f"{_word(fam['H3']['holm_rejects'], 'rejects', 'does not reject')}.")
    holds = _word(h3["prediction_holds"], "holds", "does not hold")
    L = ["### H3: little residual cost of multi-turn structure when the fact survives", "",
         "| Arm (NR, far; observed and derived pooled) | Success |", "|---|---|",
         f"| Single-turn control | {_rate_s(h3['cells']['single-turn'])} |",
         f"| F-0 multi-turn | {_rate_s(h3['cells']['F-0'])} |", "",
         (f"**Δ_H3 = p(single-turn) − p(F-0) = {_pp(h3['delta_h3']['estimate'])}**, 90% CI "
          f"{_ci(h3['delta_h3'])}, 95% CI {_ci(h3['delta_h3'], 'ci95')}."), "",
         (f"- Prediction (90% upper bound ≤ 5pp, §3 H3): **{holds}** (reported either way)"
          + ("; the whole 90% CI lies above 5pp." if h3.get("ci90_above_margin") else ".")),
         (f"- One-sided bootstrap test, H0: Δ_H3 ≥ 5pp: p = {_num_s(h3['p_one_sided'], 4)}. "
          f"{test3}"),
         ("- Model check (§9.4, as registered: a statsmodels binomial GLM with template fixed "
          "effects and the arm on the H3 cells; its probability-scale Δ_H3 is the arm's "
          f"average marginal effect over all {mc3.get('n_pairs')} (template, task cell) pairs, "
          "a template without outcome variation adding 0, reading 15): "
          f"{_pp(mc3['ame'])}; below 5pp: **{_yes(mc3['agrees'])}**. Over the "
          f"{mc3.get('n_pairs_informative')} pairs of the templates with outcome variation "
          f"only: {_pp(mc3.get('ame_informative'))}. Templates with outcome variation: "
          f"{h['glm_h3'].get('n_templates_informative')}"
          + (". With one, the model is saturated in it, so its AME is the observed Δ_H3 by "
             "construction and the check adds nothing beyond the bootstrap's point estimate; "
             "the AME over that template's pairs is its own observed difference; no "
             "cluster-robust SE" if h["glm_h3"].get("n_templates_informative") == 1 else
             f" ({h['glm_h3']['note']})" if h["glm_h3"].get("note") else "") + "."),
         ("- Logit scale (§9.3): the arm coefficient "
          + _logit_s(mc3["arm_logit"], mc3["arm_logit_status"],
                     {"ci90": mc3.get("arm_logit_ci90")})
          + (f"; no outcome variation: {'; '.join(mc3['arm_no_variation'])}"
             if mc3["arm_logit_status"] != FINITE else "") + "."),
         ("- Sensitivity (not a decision): power_sim's model (template fixed effects + derived "
          f"term + arm), AME {_pp(mc3['powersim_ame'])}"
          + (" (power_sim's Newton steps failed; statsmodels fitted it)"
             if h["glm_h3_powersim"].get("emulation_route") == "statsmodels" else "")
          + ("; power_sim's own check (`ps.h3_glm_ame`), which the simulation used, needs two "
             "templates with outcome variation and gives no estimate here"
             if h["glm_h3_powersim"].get("n_templates_informative") == 1 else "")
          + "; below 5pp: "
          f"{_yes(mc3['powersim_agrees'])}"
          + ("; **it disagrees with the registered model about the 5pp bound**."
             if mc3["powersim_disagrees"] else "."))]
    if rep:
        L.append(f"- **H3, replication (R8): {fam['H3']['label']}.** Outside luna's Holm "
                 "family and with no confirmatory label (R8): it neither confirms nor refutes "
                 "H3, and luna stays primary.")
    else:
        L.append(f"- **H3: {fam['H3']['verdict']}.** Supported needs the Holm test and the "
                 f"model check (§9.4): {_yes(fam['H3']['holm_rejects'])} and "
                 f"{_yes(fam['H3']['model_agrees'])}.")
    if h3["scales_disagree_in_sign"]:
        L.append("- **The probability and logit scales disagree in sign** (§9.3).")
    L += ["", "Per cell: " + "; ".join(
        (f"{tc}: single-turn {_rate_s(v['single-turn'])}, F-0 {_rate_s(v['F-0'])}, "
         f"difference {_pp(v['difference']['estimate'])} {_ci(v['difference'])}")
        for tc, v in h3["per_cell"].items()) + "."]
    return L


def _power_s(power: list[dict]) -> str:
    return "; ".join(f"{p['scenario']}: H1 {p['power_h1']:.3f}, H3 {p['power_h3']:.3f}"
                     for p in power)


def _f0_levels(power: list[dict]) -> str:
    return " and ".join(f"{p['p_f0_observed_far']:.2f} ({p['scenario']})" for p in power
                        if p.get("p_f0_observed_far") is not None)


def _family_lines(h: dict) -> list[str]:
    fam = h["family"]
    f2, f4 = fam["family_of_2"], fam["family_of_4_sensitivity"]
    L = ["### Multiplicity (§9.4; R6 change 9)", "",
         ("| Test | One-sided p | Holm-adjusted p, family of 2 | Rejects | "
          "Family of 4 (sensitivity) | Rejects |"), "|---|---|---|---|---|---|"]
    for i, name in enumerate(("H1 (H0: Δ_H1 ≤ 0)", "H3 (H0: Δ_H3 ≥ 5pp)")):
        L.append(f"| {name} | {_num_s(f2['pvalues'][i], 4)} | {_num_s(f2['adjusted'][i], 4)} "
                 f"| {_yes(f2['reject'][i])} | {_num_s(f4['adjusted'][i], 4)} | "
                 f"{_yes(f4['reject'][i])} |")
    L += ["", ("The family of 2 is the researcher's decision of 2026-10-06 (R6 change 9); the "
               "family of 4 counts H2's two tests, not run (R3), as not rejected. Supported in "
               f"the family of 4: H1 {_yes(fam['H1']['supported_family_of_4'])}, H3 "
               f"{_yes(fam['H3']['supported_family_of_4'])}.")]
    power = h["achieved_power"]
    if power:
        L += ["", (f"Achieved power at T = {power[0]['T_set']}, worst Holm step (one-sided "
                   f"0.025), P(supported), from `{power[0]['source']}`: {_power_s(power)}. "
                   f"Simulated with F-0 observed-far success at {_f0_levels(power)} and with "
                   "power_sim's model checks (H1: a 4-cell stand-in read through the stopping "
                   "rule; H3: template fixed effects + derived term + arm), not the ones used "
                   "here. They describe the design's scenarios, not this sweep, and P(supported) "
                   "here may differ from them" + _power_gaps(h) + ".")]
    return L


def _replication_power_s(h: dict) -> str:
    """The replication's power line (R8), or why it is unavailable."""
    pw = h["power"]
    if not pw.get("available"):
        return (f"Power at T = {pw.get('T')} (R8: one-sided 0.05, simulated with "
                "`analysis.power_sim` from Haiku's validity runs): unavailable "
                f"({pw.get('note') or 'no note'}).")
    parts = []
    for r in pw["rows"]:
        f0 = (f", F-0 observed-far at {r['p_f0_onr']:.2f} (NR) and {r['p_f0_or']:.2f} (R)"
              if r.get("p_f0_onr") is not None and r.get("p_f0_or") is not None else "")
        parts.append(f"{r['scenario']}{f0}: the unadjusted test rejects, H1 "
                     f"{r['power_h1_rejects']:.3f} and H3 {r['power_h3_rejects']:.3f}; it "
                     "rejects and the model check agrees, H1 "
                     f"{r['power_h1_rejects_and_model_agrees']:.3f} and H3 "
                     f"{r['power_h3_rejects_and_model_agrees']:.3f}")
    return (f"Power at T = {pw['T']} (R8: one-sided 0.05; from `{pw['source']}`, simulated with "
            "power_sim's model checks, H1: a 4-cell stand-in read through the stopping rule, "
            f"H3: template fixed effects + derived term + arm): {'; '.join(parts)}. It "
            "describes the simulation's scenarios, not these runs, and did not set T (R8)"
            + _power_gaps(h) + ".")


def _replication_lines(h: dict) -> list[str]:
    rp = h["replication"]
    L = ["### Multiplicity (§9.4; R8)", "",
         "| Test | One-sided p, unadjusted | Rejects at 0.05 | Model check agrees | Label |",
         "|---|---|---|---|---|"]
    for key, name in (("H1", "H1 (H0: Δ_H1 ≤ 0)"), ("H3", "H3 (H0: Δ_H3 ≥ 5pp)")):
        t = rp[key]
        L.append(f"| {name} | {_num_s(t['p_one_sided'], 4)} | {_yes(t['rejects_unadjusted'])} "
                 f"| {_yes(t['model_agrees'])} | {t['label']} |")
    L += ["", ("Outside luna's Holm family (R8; R6 change 9): luna's family stays H1 and H3 on "
               "luna, 2 tests, with the family of 4 as its sensitivity analysis, and these "
               "tests change neither its size nor its membership. They carry no confirmatory "
               "label: they neither confirm nor kill H1 or H3, and H1's kill rule and D38 read "
               "luna only."), "", _replication_power_s(h)]
    return L


def _accounting_lines(h: dict) -> list[str]:
    rep = _rep(h)
    others = [c for c in _cells_of(h) if c != "F-0"]
    L = ["## §2.8 accounting by cell (base episodes, repeat 0)", "",
         ("| Cell | Task cell | n | S_planned | S_verbatim 1/0 | S = 1 | Near losses | "
          "P(carried) | P(used \\| carried) | Rescued, lookup | Rescued, no lookup | "
          "Residual at S = 1 |"), "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in h["accounting"]:
        pc = r["P_carried"]
        carried = "-" if pc is None else f"{_num_s(pc['rate'])} ({pc['carried']}/{pc['n']})"
        used = "-" if r["used_given_carried"] is None else _rate_s(r["used_given_carried"])
        L.append(
            f"| {r['cell']}{' (expl.)' if r['exploratory'] else ''} | {r['task_cell']} | "
            f"{r['n']} | {'unset' if r['S_planned'] is None else r['S_planned']} | "
            f"{r['S_verbatim_1']}/{r['S_verbatim_0']} | {r['S_1']} | "
            f"{'-' if r['near_losses'] is None else r['near_losses']} | {carried} | {used} | "
            f"{_rate_s(r['rescued_with_lookup'])} | {_rate_s(r['rescued_without_lookup'])} | "
            f"{_rate_s(r['residual_at_S1'])} |")
    if rep:
        carry = [c for c in others if c in CARRY_CELLS]
        L += ["", ("Rescued = success among S_verbatim = 0"
                   + (f" (and, in {' and '.join(carry)}, not carried)" if carry else "")
                   + "; chance is 0.10."
                   + (" P(carried) is a lower bound: the string match misses paraphrase "
                      "(§2.8)." if carry else "")
                   + " Near losses are expected, not bugs, and stay in their cell (§13).")]
    else:
        L += ["", ("Rescued = success among S_verbatim = 0 (and, in W-n-0 and Σ-n-0, not "
                   "carried); chance is 0.10. P(carried) is a lower bound: the string match "
                   "misses paraphrase (§2.8). Near losses are expected, not bugs, and stay in "
                   "their cell (§13). Σ-n-0 is exploratory (D12, §9.10); its split by "
                   "`compacted_between` is in h1h3.json.")]
    heads = [f"{c} (expl.)" if c in SUMMARY_CELLS else c for c in others]
    L += ["", "## Cost outcomes (§9.5): ratio to F-0 in the same task cell", "",
          ("Quasi-Poisson log-link GLM with template fixed effects (§9.5); ratio exp(β) [95% "
           "CI]. §9.5 registers the model, not a comparison: each harness cell against F-0 "
           "within a task cell is this script's reading 11 (as implemented, not registered)."),
          "", "| Task cell | Outcome | " + " | ".join(heads) + " |",
          "|---|---|" + "---|" * len(heads)]
    for r in h["cost_outcomes"]:
        cells = []
        for c in others:
            x = r["ratios"].get(c)
            if r.get("unavailable"):
                cells.append("unavailable (not reported)")
                continue
            if x is None:
                cells.append("n/a" + (" (no F-0 events)" if "reference" in (r.get("note") or "")
                                      else ""))
                continue
            if x.get("note"):
                cells.append("0 (no events)")
                continue
            ci = x["ratio_ci95"]
            cells.append(f"{x['ratio']:.3f}"
                         + ("" if ci is None else f" [{ci[0]:.3f}, {ci[1]:.3f}]"))
        L.append(f"| {r['task_cell']} | {r['label']} | " + " | ".join(cells) + " |")
    missing = [r for r in h["cost_outcomes"] if r.get("n_missing") and not r.get("unavailable")]
    if missing:
        L += ["", ("Fitted on the episodes that report the outcome: "
                   + "; ".join(f"{r['task_cell']} {r['label']}, {r['n_missing']} missing"
                               for r in missing) + ".")]
    return L


def _stopped_s(r: dict) -> str:
    """The replication's stopped step responses of a cell, by reason (R8: refusals per cell,
    with their category)."""
    st = r.get("stopped_responses") or {}
    return (", ".join(f"{k} {v}" for k, v in st.items()) or "-") + (
        f" ({r['episodes_with_a_refusal']} episode(s) with a refusal)"
        if r.get("episodes_with_a_refusal") else "")


def _tables_lines(h: dict) -> list[str]:
    rep = _rep(h)
    if rep:
        L = ["## Success by cell (repeat 0; descriptive)", "",
             ("Descriptive, not tests (§9.10): each cell's success rate. Only the contrasts "
              "above are registered; the restated-at-need control (the memory-free ceiling, "
              "§4.3) and the W cells' derived and near cells enter no registered test here. "
              "Stopped responses are the step responses that stopped short, by reason (a "
              "refusal with its category, `max_output_tokens` at the output cap): each is an "
              "invalid action that scores 0 and stays in (R8)."), "",
             "| Run kind | Task cell | Success | Content failures | Stopped responses |",
             "|---|---|---|---|---|"]
    else:
        L = ["## Success by cell (repeat 0; descriptive)", "",
             ("Descriptive, not tests (§9.10): each cell's success rate. Only the contrasts "
              "above are registered; the restated-at-need control (the memory-free ceiling, "
              "§4.3), the W cells' derived and near cells and the Σ-n-0 cells (exploratory, "
              "D12) enter no registered test here."), "",
             "| Run kind | Task cell | Success | Content failures |", "|---|---|---|---|"]
    for r in h["cells"]:
        cf = ", ".join(f"{k} {v}" for k, v in r["content_failures"].items()) or "-"
        L.append(f"| {r['kind']}{' (expl.)' if r['exploratory'] else ''} | {r['task_cell']} | "
                 f"{_rate_s(r)} | {cf} |" + (f" {_stopped_s(r)} |" if rep else ""))
    runner = "excluded_echo" if not rep else "excluded_by_runner"
    ex = [e for e in h["exclusions"] if e[runner] or e["excluded_transport"]
          or e["excluded_no_final"] or e["never_played"] or e["pending"]
          or e["dropped_duplicates"]]
    L += ["", "## Exclusions and duplicates (§13; DESIGN §7.8)", ""]
    if ex:
        L += [(f"| Run kind | Task cell | Keys | Never played | "
               f"{'Excluded by the runner' if rep else 'Echo excluded'} | Transport "
               "excluded | No final record (closed) | Pending | Dropped duplicates |"),
              "|---|---|---|---|---|---|---|---|---|"]
        L += [(f"| {e['kind']} | {e['task_cell']} | {e['keys']} | {e['never_played']} | "
               f"{e[runner]}{' (**over 5%**)' if e.get('echo_over_5pct') else ''} | "
               f"{e['excluded_transport']} | {e['excluded_no_final']} | {e['pending']} | "
               f"{e['dropped_duplicates']} |") for e in ex]
    else:
        L.append("None: every repeat-0 key has one final record, and none is excluded.")
    if rep:
        L += ["", ("No echo exclusion (R8): the Messages API echoes neither effort nor a "
                   "reasoning context. Its substitutes, the payload snapshot tests and the "
                   "request-side check of every request, act before a request is sent.")]
    L += ["", "## Repeats (§2.9; descriptive, not in any primary result)", "",
          "| Run kind | Episode pairs | Agreement | Success at repeat 0 only | at repeat 1 only |",
          "|---|---|---|---|---|"]
    L += [(f"| {r['kind']} | {r['pairs']} | {_num_s(r['agreement'])} | "
           f"{r['repeat0_only_success']} | {r['repeat1_only_success']} |")
          for r in h["repeats"]]
    ms = h["model_strings"]
    L += ["", "## Runs", "", ("Model strings returned: " + ", ".join(
        f"`{k or 'none'}` ({v})" for k, v in ms["strings"].items()) + ".")]
    if ms["split"]:
        L += ["", ("**More than one model string** (§6): Δ_H1 and Δ_H3 per group of records "
                   "(90% CIs on the same resamples; reading 12)."), "",
              "| Group | Episodes | Δ_H1 | Δ_H3 |", "|---|---|---|---|"]
        L += [(f"| `{k}` | {v['episodes']} | {_pp(v['delta_h1']['estimate'])} "
               f"{_ci(v['delta_h1'])} | {_pp(v['delta_h3']['estimate'])} "
               f"{_ci(v['delta_h3'])} |") for k, v in ms["split"].items()]
    L += ["", "| Run | Cell | Variants | Repeat | Started | Exit | Records | Counted |",
          "|---|---|---|---|---|---|---|---|"]
    L += [(f"| `{r['run_id']}` | {r['cell']} | {', '.join(r['variants'])} | "
           f"{r['repeat_index']} | {r['started_utc']} | {r['exit_reason']} | {r['records']} | "
           f"{r['records_counted']} |") for r in h["inputs"]["runs"]]
    if h["inputs"]["rerun_links"]:
        L.append("Re-run and continuation links (--rerun): " + ", ".join(
            f"`{k}` of `{v}`" for k, v in h["inputs"]["rerun_links"].items()) + ".")
    if h["warnings"] or h["inputs"]["skipped"]:
        L += ["", "## Checks", ""]
        L += [f"- {w}" for w in h["warnings"]]
        L += [f"- skipped `{s['folder']}`: {s['reason']}" for s in h["inputs"]["skipped"]]
    return L


def summary_lines(h: dict) -> list[str]:
    rep = _rep(h)
    inputs = ("the runs named with --run" if h["inputs"].get("input_list") is not None
              else f"every {_name_of(h)} run found (no --run input list)")
    title = ("# H1 and H3 on claude-haiku-5-5's PersistGym runs: R8's replication (PREREG "
             "§17.8)" if rep else
             "# H1 and H3 on gpt-6-luna's PersistGym sweep (PREREG §3 H1, §3 H3; R6)")
    command = ("`uv run python -m analysis.persistgym_h1h3`" if not rep else
               f"`uv run python -m analysis.persistgym_h1h3 --model {h['model']}`")
    L = [title, "",
         (f"Computed {h['generated_utc']} at commit {h['git_commit'][:7]} (dirty: "
          f"{h['git_dirty']}) by {command}, from "
          f"`{h['inputs']['results_root']}` ({inputs}). Templates 0-{h['templates'] - 1}, "
          f"repeat 0, {h['primary_episodes']} primary episodes. Bootstrap: "
          f"{h['bootstrap']['resamples']:,} template resamples, percentile intervals, RNG "
          f"seed SEED + {BOOT_SEED_OFFSET} = {h['bootstrap']['seed']}. H1's model-check rule "
          f"for a non-finite logit-scale Δ_H1: `{h['h1_separation_rule']}`."), "",
         f"**Status: {h['status']}.**", ""]
    if rep:
        prof = h["profile"]
        L += [("**A replication** (PREREG §17.8, amendment R8), reported in full whatever the "
               "outcome: every H1 and H3 quantity of §3 is computed on "
               f"{h['model']}'s episodes (experiment `{prof['experiment']}`, cells "
               f"{', '.join(prof['cells'])}, the restated-at-need control and the single-turn "
               "control) exactly as on luna's, with the same predictions, thresholds and model "
               "checks. Its tests are outside luna's Holm family: unadjusted one-sided "
               "bootstrap p-values and the model checks, with no confirmatory label. luna stays "
               f"primary (`{LUNA_CITED_OUTPUT}`), and these episodes are never pooled with "
               "luna's."), "",
              ("**Pre-specified rules** (fixed for luna on 2026-10-10, after luna's data and "
               "before any Haiku data; R8): "
               + "; ".join(h.get("pre_specified") or PRE_SPECIFIED) + ".")]
        if prof["cells_not_run"]:
            L += ["", (f"**{', '.join(prof['cells_not_run'])}: {NOT_RUN_BUDGET}** (R8's size "
                       "rule; `registered.HAIKU_CELLS`).")]
    else:
        L.append("**Changed after the FINAL output of 2026-10-10 was read** (the researcher's "
                 "decisions, `results/decisions.md`; the outputs before the changes are kept): "
                 + "; ".join(h.get("changed_after_final") or CHANGED_AFTER_FINAL) + ".")
    if h["provisional_reasons"]:
        L += ["", "Not the registered analysis, so no confirmatory claim is made from it:"]
        L += [f"- {x}" for x in h["provisional_reasons"]]
    if h.get("sweep_closed") is not None or h.get("deviations"):
        L += ["", "## Deviations (§13: listed in every write-up)", ""]
        if h.get("sweep_closed") is not None:
            L.append(f"- The sweep was closed by the researcher ({h['sweep_closed']}); keys "
                     "with no final record and keys never played are excluded (DESIGN §7.8).")
        L += [f"- {x}" for x in h.get("deviations") or []]
    ac = h["accounting_check"]
    if ac["missing_transcripts"]:
        check = ("§2.8 accounting check: the far-distance condition passed; the replay could "
                 f"not be made for {', '.join(ac['missing_transcripts'])} (no transcript).")
    else:
        check = (f"§2.8 accounting check: passed on {ac['checked']} window-cell episodes (no "
                 "far window episode with S_verbatim = 1; S_verbatim equals the drop-oldest "
                 "replay in every one).")
    if rep:
        check += (" The replay read the Messages transcripts: each turn's reply as the session "
                  "kept it, the empty text for a refusal, so a turn sent back as `(no reply)` "
                  "counts 0 tokens.")
    L += ["", check, "", "## Replication (R8; outside luna's Holm family)" if rep
          else "## Confirmatory", ""]
    L += _h1_lines(h) + [""] + _h3_lines(h) + [""]
    L += _replication_lines(h) if rep else _family_lines(h)
    L += [""] + _accounting_lines(h) + [""] + _tables_lines(h) + [""]
    L += not_shown_r8_lines(h) if rep else not_shown_lines(h)
    return L


def _dated(strings, model: str = MODEL) -> bool:
    """Whether a returned model string is a dated snapshot of `model`'s (`model_family`)."""
    return any(s != model and registered.model_family(s) == model for s in strings)


def _power_gaps(h: dict) -> str:
    """The cases of this sweep that power_sim's scenarios did not simulate."""
    gaps = []
    if (h.get("glm_9_1") or {}).get("logit_status", FINITE) != FINITE:
        gaps.append("H1's model check meets separation and is read by the rule in force "
                    f"(`{h['h1_separation_rule']}`), which power_sim did not simulate")
    if (h.get("glm_h3") or {}).get("n_templates_informative") == 1:
        gaps.append("H3's cells have one template with outcome variation, where power_sim's "
                    "own H3 check gives no estimate")
    return (": " + "; ".join(gaps)) if gaps else ""


def not_shown_lines(h: dict) -> list[str]:
    """"What it does not show", in substance from §15, with this reading's numbers."""
    power = h.get("achieved_power") or []
    singles = sorted({s for k in h["model_strings"]["strings"] for s in k.split("|") if s})
    strings = ", ".join(f"`{s}`" for s in singles) or "none"
    snapshot = ("a dated snapshot among the strings returned" if _dated(singles)
                else "no dated snapshot")
    power_s = ""
    if power:
        power_s = (f"; the achieved power at the worst Holm step was {_power_s(power)} (H1 at "
                   "Δ_H1 = 10pp, H3 at Δ_H3 = 0), simulated with F-0 observed-far success at "
                   f"{_f0_levels(power)} and with power_sim's model checks; it describes the "
                   "design's scenarios, not this sweep, and P(supported) here may differ from "
                   "it" + _power_gaps(h))
    return [
        "## What it does not show", "",
        ("- **Not a model comparison.** One model, gpt-6-luna, at medium effort on Flex, with "
         f"{snapshot} (returned: {strings}). Nothing here ranks models or vendors; the effects "
         "are against task properties (recoverability, distance)."),
        ("- **PersistGym is synthetic.** The results are not claimed to transfer to coding "
         "agents, ARC or real tasks. Window effects at S = 0 are mechanical, not findings in "
         "themselves: Penalty_NR is a manipulation check, and the confirmatory quantity is the "
         "difference of penalties."),
        ("- **Non-inferiority is not absence.** Where H3's bound holds, it says the "
         "single-prompt arm is at most 5pp ahead at the stated confidence, not that the "
         "multi-turn structure costs nothing. A result that is neither supported nor killed "
         "is inconclusive, not \"no effect\"" + power_s + "."),
        ("- **H3's control favours itself a little.** It uses the oracle's routine replies, so "
         "its evidence-to-need gaps are slightly shorter than with real replies (§3 H3)."),
        ("- **R_need reinterprets PLAN's \"total tokens\"** (D8): it follows need-phase calls "
         "and is driven largely by the same behaviour as the lookups prediction; the literal "
         "episode ratio cannot reach 1.30 by design."),
        ("- **P(carried) is a lower bound** (string match misses paraphrased carry), and Σ-cell "
         "results are exploratory (D12)."),
        ("- **Not run:** H2 (stopped under R3), sol's replication of H1 (R6), the failure "
         "labels (R6)."),
        ("- **Costs are period-specific:** provider-reported tokens at the prices checked on "
         "2026-09-29/30, Flex tier.")]


def not_shown_r8_lines(h: dict) -> list[str]:
    """"What it does not show" for R8's replication: R8's list (PREREG §17.8), with §15's
    points that carry over and this reading's model strings."""
    model = h["model"]
    singles = sorted({s for k in h["model_strings"]["strings"] for s in k.split("|") if s})
    strings = ", ".join(f"`{s}`" for s in singles) or "none"
    snapshot = ("a dated snapshot among the strings returned" if _dated(singles, model)
                else "no dated snapshot")
    not_run = h["profile"]["cells_not_run"]
    return [
        "## What it does not show", "",
        (f"- **Not a model comparison.** One model of a second provider, {model}, at "
         f"{registered.registered_effort(model)} effort on the standard Messages path, with "
         f"{snapshot} (returned: {strings}). It "
         "ranks neither the models nor their providers: each model's harness effects are "
         "reported against task properties (fact kind, recoverability, distance), in the same "
         "form for both, and no contrast between the two models is tested or plotted as a "
         "ranking. Differences between their effects are described, not tested (§15)."),
        ("- **One model per provider.** The provider, the model, its training, its reasoning, "
         "and the API and serving path all differ at once: a difference between the two models "
         "cannot be attributed to any one of them, and agreement says nothing about other "
         "models or providers."),
        ("- **Not a second confirmation.** Agreement with luna is a replication outside the "
         "Holm family; disagreement is stated, both results are reported side by side, and "
         "neither overrides the other."),
        ("- **The same synthetic task family.** Haiku plays luna's episodes, so luna's limits "
         "carry over: PersistGym is synthetic, the results are not claimed to transfer to "
         "coding agents, ARC or real tasks, and window effects at S = 0 are mechanical "
         "(Penalty_NR is a manipulation check). If both models are at the ceiling in H3's "
         "cells, H3 says nothing about harder tasks."),
        ("- **Non-inferiority is not absence.** Where H3's bound holds, it says the "
         "single-prompt arm is at most 5pp ahead at the stated confidence, not that the "
         "multi-turn structure costs nothing; and H3's control uses the oracle's routine "
         "replies, so its evidence-to-need gaps are slightly shorter than with real replies "
         "(§3 H3)."),
        ("- **R_need reinterprets PLAN's \"total tokens\"** (D8), and P(carried) is a lower "
         "bound (string match misses paraphrased carry)."),
        ("- **Not blind to luna.** R8's design and its pre-specified rules were chosen with "
         "luna's results known."),
        ("- **Costs and tokens are not comparable** across the two models: each is in its own "
         "provider's tokens and prices (here Anthropic's, at the prices checked on 2026-10-17, "
         "standard tier, no Flex). W and every planned distance stay in project tokens."),
        ("- **Thinking is not inspected.** Its display is omitted, so only its token counts "
         "are seen, where reported."),
        ("- **Not run on this model:** Σ-n-0 and every replay-on cell (R8)"
         + (f"; {', '.join(not_run)} ({NOT_RUN_BUDGET})" if not_run else "") + ".")]


# --- main ----------------------------------------------------------------------------------

def _json_default(o):
    if isinstance(o, Fraction):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def _clean(o):
    """NaN and infinities become null (JSON has neither)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def write(out_dir: Path, run_id: str, h: dict, text: str, git: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "h1h3.json").write_text(
        json.dumps(_clean(h), indent=2, ensure_ascii=False, default=_json_default) + "\n",
        encoding="utf-8", newline="\n")
    (out_dir / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    rep = _rep(h)
    config = {"prereg": (R8_PREREG if rep else
                         "PREREG.md §3 H1, §3 H3, §2.8, §2.9, §9.1-§9.5, §13; R2 change 3, "
                         "R6 changes 1, 6 and 9"),
              "model": h["model"], "generator_config_hash": h["generator_config_hash"],
              **({"experiment_read": h["profile"]["experiment"],
                  "cells": h["profile"]["cells"],
                  "cells_not_run": h["profile"]["cells_not_run"],
                  "power_source": h["power"]["source"]} if rep else {}),
              "templates": h["templates"], "n_boot": h["bootstrap"]["resamples"],
              "bootstrap_seed": h["bootstrap"]["seed"], "levels": list(LEVELS),
              "status": h["status"], "rerun_links": h["inputs"]["rerun_links"],
              "sweep_closed": h["sweep_closed"], "h1_separation_rule": h["h1_separation_rule"],
              "bayesian_glmm": {k: h["bayesian_glmm"].get(k) for k in (
                  "status", "model", "priors", "seed", "chains", "draws", "tune", "versions")},
              "inputs": {k: v for k, v in h["inputs"].items() if k != "runs"}}
    return runmeta.write_meta(
        out_dir, git=git, experiment=h["profile"]["out_name"] if rep else OUT_NAME,
        run_id=run_id, cell_or_config="h1h3",
        config=_clean(config), model_requested=None, model_returned=None,
        reasoning_effort=None, reasoning_context_requested=None,
        reasoning_context_echoed=None, template_id=None, repeat_index=None,
        seeds={"bootstrap": h["bootstrap"]["seed"],
               "bayesian_glmm": h["seed"] + BAYES_SEED_OFFSET},
        started_utc=h["generated_utc"],
        finished_utc=runmeta.utc_now(),
        exit_reason="completed" if h["status"] == FINAL else "completed_provisional",
        tokens=None, cost_usd=0.0, raw_transcript_path=None, outputs=list(OUTPUTS),
        paid_calls=0, runs=[r["run_id"] for r in h["inputs"]["runs"]])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results-root", type=Path, default=RESULTS,
                    help="the results folder to read (default: this checkout's results/)")
    ap.add_argument("--raw-root", type=Path, default=None,
                    help="where the raw transcripts are (default: <results root>/raw)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help=f"default: <results root>/{OUT_NAME}/<UTC>/ ({MODEL}) or "
                         f"<results root>/{HAIKU_OUT_NAME}/<UTC>/ ({registered.HAIKU_MODEL})")
    ap.add_argument("--no-write", action="store_true", help="print only")
    ap.add_argument("--boot", type=int, default=N_BOOT,
                    help="bootstrap resamples (registered: 10,000; any other is PROVISIONAL)")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="report what exists (PROVISIONAL) while the sweep is incomplete")
    ap.add_argument("--rerun", action="append", metavar="RUN=ORIGINAL",
                    help="declare RUN a re-run or continuation of ORIGINAL, as listed in "
                         "results/decisions.md (harnesses/DESIGN.md §7.8); repeatable")
    ap.add_argument("--run", action="append", metavar="RUN_ID", dest="runs",
                    help="a run to read; name every run (harnesses/DESIGN.md §7.8); without "
                         "any, every run of the model found is read and the output is "
                         "PROVISIONAL")
    ap.add_argument("--sweep-closed", metavar="REF", default=None,
                    help="the results/decisions.md entry in which the researcher closed the "
                         "sweep: keys with no final record, and keys never played, are then "
                         "excluded (DESIGN §7.8) and listed as deviations")
    ap.add_argument("--no-bayes", action="store_true",
                    help="skip §9.1's Bayesian sensitivity fit (PROVISIONAL)")
    ap.add_argument("--model", choices=(MODEL, registered.HAIKU_MODEL), default=MODEL,
                    help=f"whose runs to analyse: {MODEL}'s pre-registered sweep (default) or "
                         f"{registered.HAIKU_MODEL}'s replication under R8 (PREREG §17.8)")
    ap.add_argument("--experiment", default=None,
                    help=f"the experiment folder to read (default: the model's registered one, "
                         f"{EXPERIMENT} or {registered.HAIKU_EXPERIMENT}; any other is "
                         "PROVISIONAL)")
    ap.add_argument("--power-path", type=Path, default=None,
                    help=f"the power file (default for {MODEL}: its committed power run; for "
                         f"{registered.HAIKU_MODEL}, a per-T power table of power_sim's luna "
                         "part, luna_power.csv, simulated with Haiku's assumptions; without "
                         "one its power is reported as unavailable)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if a.boot < 1:
        print("--boot must be at least 1", file=sys.stderr)
        return 2
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = a.results_root.resolve()
    try:
        links = parse_links(a.rerun)
        prof = profile(a.model, a.experiment)
        git = runmeta.git_state()
        h = compute(root, now.isoformat(timespec="seconds"), git, boot=a.boot,
                    allow_incomplete=a.allow_incomplete,
                    raw_root=a.raw_root.resolve() if a.raw_root else None, links=links,
                    runs=a.runs, sweep_closed=a.sweep_closed, bayes=not a.no_bayes,
                    model=a.model, experiment=a.experiment,
                    power_path=a.power_path.resolve() if a.power_path else None)
    except AccountingBug as e:
        print(f"H1/H3 stopped: {e}", file=sys.stderr)
        return 2
    except Refusal as e:
        print(f"H1/H3 refused: {e}", file=sys.stderr)
        return 2
    text = "\n".join(summary_lines(h)) + "\n"
    print(text)
    if not a.no_write:
        out = a.out_dir or root / prof.out_name / run_id
        write(out, run_id, h, text, git)
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
