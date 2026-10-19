# Descriptive readings behind the replication's report (not tests)

Counted records at repeat 0, as each model's cited H1/H3 output counted them (DESIGN §7.8). Descriptive only: no contrast between the models is tested (§15, R8).

## gpt-6-luna (`results/persistgym_h1h3/20261010T232227Z`)

| W-0 cell | Episodes | Chose an option | Correct | Chose none: need outcomes |
|---|---|---|---|---|
| observed-nonrec-far | 200 | 198 | 15 | wrong 2 |
| derived-nonrec-far | 200 | 189 | 16 | wrong 11 |

| Run kind | Episodes | With a refusal | Need-step refusals | Categories |
|---|---|---|---|---|
| F-0 | 1600 | 0 (0.00%) | 0 | - |
| F-0 restated | 1600 | 0 (0.00%) | 0 | - |
| W-0 | 1600 | 0 (0.00%) | 0 | - |
| W-n-0 | 1600 | 0 (0.00%) | 0 | - |
| single-turn | 800 | 0 (0.00%) | 0 | - |
| Σ-n-0 | 1600 | 0 (0.00%) | 0 | - |

Templates with a refused episode: 0; by skin: none.

## claude-haiku-5-5 (`results/persistgym_h1h3_haiku/20261019T003254Z`)

| W-0 cell | Episodes | Chose an option | Correct | Chose none: need outcomes |
|---|---|---|---|---|
| observed-nonrec-far | 200 | 0 | 0 | incomplete 1, unparsed 177, wrong 22 |
| derived-nonrec-far | 200 | 0 | 0 | incomplete 1, unparsed 172, wrong 27 |

| Run kind | Episodes | With a refusal | Need-step refusals | Categories |
|---|---|---|---|---|
| F-0 | 1600 | 22 (1.38%) | 10 | refusal:bio 69 |
| F-0 restated | 1600 | 17 (1.06%) | 6 | refusal:bio 48 |
| W-0 | 1600 | 26 (1.62%) | 2 | refusal:bio 48 |
| single-turn | 800 | 1 (0.12%) | 1 | refusal:bio 1 |

Templates with a refused episode: 14; by skin: archive 1, biobank 13.

`main-000034` biobank (2); `main-000044` biobank (1); `main-000069` biobank (3); `main-000087` biobank (7); `main-000088` biobank (1); `main-000119` biobank (2); `main-000122` biobank (1); `main-000145` biobank (13); `main-000157` archive (2); `main-000162` biobank (3); `main-000166` biobank (8); `main-000167` biobank (2); `main-000171` biobank (1); `main-000193` biobank (20).

