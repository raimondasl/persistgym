# Latency in the study's records (exploratory)

Produced by `analysis/latency_ledger.py`. Its docstring says what these numbers are not. PREREG registers no latency outcome.

## arc_configs

| config | n_counted_runs | games | s_per_action_min | s_per_action_max | s_per_action_median | median_s_per_call_min | median_s_per_call_max | median_s_per_call_median | wall_clock_h_max | n_clock_endings | reasoning_tokens_per_action_min | reasoning_tokens_per_action_max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 | 4 | cd82 ft09 r11l sb26 | 76.4 | 202.3 | 175.3 | 50.977 | 175.953 | 163.37 | 12.03 | 2 | 3185 | 28403 |
| S1 | 4 | cd82 ft09 r11l sb26 | 32.6 | 111.7 | 77.1 | 15.469 | 80.797 | 33.343 | 10.09 | 0 | 3530 | 16264 |
| S2 | 4 | cd82 ft09 r11l sb26 | 53.0 | 116.7 | 108.2 | 18.14 | 93.758 | 80.984 | 9.27 | 0 | 6731 | 18173 |
| S4 | 4 | cd82 ft09 r11l sb26 | 26.7 | 59.0 | 37.9 | 9.047 | 31.547 | 15.16 | 4.61 | 0 | 2315 | 7295 |

## arc_runs

| run_id | config | game | exit_reason | rerun_of | counted | actions | n_calls | n_compactions | wall_clock_h | s_per_action | median_s_per_call | p90_s_per_call | reasoning_tokens_per_action | reasoning_tokens_per_call | output_tokens_per_call | input_tokens_per_call | retries | retry_wait_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261006T144656Z-S4-cd82-s1 | S4 | cd82 | GAME_WIN |  | True | 206 | 239 | 33 | 2.49 | 43.6 | 17.36 | 111.015 | 4671 | 4026 | 4148 | 121021 | 0 | 0.0 |
| 20261006T171726Z-S0-ft09-s1 | S0 | ft09 | TIME_BUDGET |  | False | 236 | 237 | 0 | 12.03 | 183.4 | 181.25 | 367.985 | 25513 | 25405 | 25564 | 159873 | 1 | 30.0 |
| 20261007T133444Z-S4-sb26-s1 | S4 | sb26 | GAME_WIN |  | True | 138 | 174 | 36 | 1.02 | 26.7 | 12.961 | 26.719 | 2315 | 1836 | 2028 | 131321 | 0 | 0.0 |
| 20261007T143700Z-S0-sb26-s1 | S0 | sb26 | ACTION_BUDGET |  | True | 238 | 246 | 0 | 11.01 | 166.6 | 156.679 | 283.281 | 22328 | 21602 | 21681 | 115482 | 0 | 0.0 |
| 20261008T013832Z-S0-cd82-s1 | S0 | cd82 | TIME_BUDGET |  | True | 235 | 243 | 0 | 12.01 | 184.1 | 170.062 | 280.344 | 24270 | 23471 | 23493 | 144694 | 0 | 0.0 |
| 20261008T134155Z-S0-r11l-s1 | S0 | r11l | ACTION_BUDGET |  | True | 365 | 362 | 0 | 7.75 | 76.4 | 50.977 | 178.453 | 3185 | 3211 | 10542 | 126801 | 1 | 1.889 |
| 20261008T212807Z-S4-r11l-s1 | S4 | r11l | ACTION_BUDGET |  | True | 281 | 330 | 53 | 4.61 | 59.0 | 31.547 | 105.844 | 7295 | 6212 | 6479 | 123155 | 5 | 150.0 |
| 20261009T020602Z-S4-ft09-s1 | S4 | ft09 | GAME_WIN |  | True | 112 | 122 | 10 | 1.0 | 32.3 | 9.047 | 90.563 | 4289 | 3938 | 4101 | 108020 | 0 | 0.0 |
| 20261009T030646Z-S0-ft09-s101 | S0 | ft09 | TIME_BUDGET | 20261006T171726Z-S0-ft09-s1 | True | 214 | 222 | 0 | 12.03 | 202.3 | 175.953 | 380.281 | 28403 | 27380 | 27492 | 162134 | 0 | 0.0 |
| 20261010T005046Z-S1-sb26-s1 | S1 | sb26 | GAME_WIN |  | True | 131 | 164 | 33 | 1.19 | 32.6 | 15.469 | 42.906 | 3530 | 2819 | 3113 | 127862 | 0 | 0.0 |
| 20261010T020247Z-S2-ft09-s1 | S2 | ft09 | AGENT_ERROR |  | False | 49 | 56 | 3 | 0.98 | 71.9 | 35.859 | 177.61 | 10309 | 9020 | 9151 | 97171 | 0 | 0.0 |
| 20261010T030159Z-S2-ft09-s101 | S2 | ft09 | AGENT_ERROR | 20261010T020247Z-S2-ft09-s1 | False | 112 | 133 | 9 | 4.14 | 133.2 | 85.796 | 282.281 | 21170 | 17827 | 18005 | 93173 | 1 | 1.544 |
| 20261010T071105Z-S1-ft09-s1 | S1 | ft09 | GAME_WIN |  | True | 92 | 101 | 7 | 1.63 | 63.6 | 23.406 | 161.953 | 9097 | 8287 | 8681 | 98243 | 0 | 0.0 |
| 20261010T084933Z-S2-r11l-s1 | S2 | r11l | AGENT_ERROR |  | False | 28 | 38 | 6 | 1.75 | 224.6 | 188.047 | 328.469 | 35819 | 26393 | 26624 | 118038 | 0 | 0.0 |
| 20261010T103451Z-S2-r11l-s101 | S2 | r11l | ACTION_BUDGET | 20261010T084933Z-S2-r11l-s1 | True | 286 | 334 | 46 | 9.27 | 116.7 | 93.758 | 184.562 | 17001 | 14557 | 14912 | 109994 | 0 | 0.0 |
| 20261010T202129Z-S2-ft09-s201 | S2 | ft09 | ACTION_BUDGET |  | True | 219 | 237 | 17 | 6.63 | 109.0 | 80.938 | 214.75 | 18173 | 16793 | 16883 | 92437 | 0 | 0.0 |
| 20261011T030015Z-S1-cd82-s1 | S1 | cd82 | AGENT_ERROR |  | False | 87 | 112 | 13 | 2.63 | 109.0 | 62.812 | 185.141 | 14136 | 10981 | 11311 | 106457 | 0 | 0.0 |
| 20261011T053855Z-S1-cd82-s101 | S1 | cd82 | AGENT_ERROR | 20261011T030015Z-S1-cd82-s1 | True | 210 | 255 | 31 | 5.28 | 90.5 | 43.281 | 190.89 | 13239 | 10902 | 11250 | 104880 | 0 | 0.0 |
| 20261011T105637Z-S2-cd82-s1 | S2 | cd82 | ACTION_BUDGET |  | True | 297 | 345 | 36 | 8.87 | 107.5 | 81.031 | 178.641 | 15489 | 13334 | 13433 | 98433 | 0 | 0.0 |
| 20261011T205715Z-S1-r11l-s1 | S1 | r11l | ACTION_BUDGET |  | True | 325 | 377 | 49 | 10.09 | 111.7 | 80.797 | 200.187 | 16264 | 14021 | 14357 | 107330 | 0 | 0.0 |
| 20261012T150200Z-S2-sb26-s1 | S2 | sb26 | GAME_WIN |  | True | 175 | 219 | 43 | 2.58 | 53.0 | 18.14 | 106.828 | 6731 | 5379 | 5537 | 127015 | 0 | 0.0 |

## arc_published

| harness | n_games | s_per_step_median_min | s_per_step_median_max | s_per_step_median_median | s_per_step_mean_min | s_per_step_mean_max | s_per_step_mean_median | reasoning_per_step_mean_median |
|---|---|---|---|---|---|---|---|---|
| standard | 10 | 32.9 | 131.4 | 80.1 | 49.2 | 128.3 | 83.0 | 26083 |
| provider_adapter | 10 | 4.3 | 26.3 | 5.9 | 12.1 | 40.1 | 22.1 | 4690 |

## persistgym_cells

| model | tier_served | harness_cell | variant | n_runs | n_records | n_calls | n_calls_gate_waited | median_s_per_call | median_s_per_call_runs_gate_held_none | p90_s_per_call | median_calls_per_record | median_model_s_per_record | output_tokens_per_call |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | standard | F-0 | base | 2 | 1760 | 42267 | 1475 | 0.781 | 0.766 | 1.188 | 24.0 | 20.3 | 48 |
| claude-haiku-5-5 | standard | F-0 | restated | 2 | 1760 | 42262 | 1481 | 0.766 | 0.766 | 1.125 | 24.0 | 19.8 | 46 |
| claude-haiku-5-5 | standard | W-0 | base | 4 | 1786 | 43202 | 40 | 0.891 | 0.891 | 2.016 | 24.0 | 26.2 | 54 |
| claude-haiku-5-5 | standard | W-b-0 | base | 4 | 1600 | 38858 | 0 | 0.937 | 0.937 | 1.406 | 24.0 | 24.5 | 53 |
| claude-haiku-5-5 | standard | W-n-0 | base | 6 | 2193 | 53109 | 17 | 0.954 | 0.953 | 1.687 | 24.0 | 26.3 | 93 |
| claude-haiku-5-5 | standard | W-nd-0 | base | 4 | 200 | 4812 | 0 | 1.375 | 1.375 | 2.781 | 24.0 | 38.1 | 209 |
| claude-haiku-5-5 | standard | W-np-0 | base | 6 | 1013 | 24370 | 0 | 2.187 | 2.187 | 4.156 | 24.0 | 59.4 | 554 |
| claude-haiku-5-5 | standard | W-npd-0 | base | 1 | 800 | 19300 | 0 | 2.179 | 2.179 | 4.172 | 24.0 | 60.1 | 533 |
| claude-haiku-5-5 | standard | W-nx-0 | base | 4 | 200 | 4812 | 0 | 1.125 | 1.125 | 2.0 | 24.0 | 31.0 | 108 |
| claude-haiku-5-5 | standard | single-turn | base | 5 | 886 | 886 | 0 | 1.438 | 1.438 | 1.968 | 1.0 | 1.4 | 119 |
| claude-sonnet-5-5 | standard | F-0 | base | 2 | 51 | 1264 |  | 1.562 | 1.563 | 1.922 | 25.0 | 38.8 | 50 |
| claude-sonnet-5-5 | standard | W-n-0 | base | 1 | 50 | 1242 | 0 | 2.281 | 2.281 | 3.969 | 25.0 | 61.8 | 317 |
| claude-sonnet-5-5 | standard | W-np-0 | base | 1 | 50 | 1242 | 0 | 3.063 | 3.063 | 5.968 | 25.0 | 92.0 | 488 |
| gpt-6-luna | flex | F-0 | base | 3 | 1768 | 42475 |  | 1.672 | 1.672 | 4.563 | 24.0 | 43.6 | 23 |
| gpt-6-luna | flex | F-0 | restated | 2 | 1760 | 42281 | 0 | 1.609 | 1.609 | 2.313 | 24.0 | 41.4 | 23 |
| gpt-6-luna | flex | W-0 | base | 2 | 1760 | 42711 | 0 | 1.375 | 1.375 | 1.969 | 24.0 | 37.2 | 30 |
| gpt-6-luna | flex | W-n-0 | base | 2 | 1760 | 42658 | 0 | 1.641 | 1.641 | 2.891 | 24.0 | 45.8 | 38 |
| gpt-6-luna | flex | single-turn | base | 2 | 880 | 880 | 0 | 2.062 | 2.062 | 2.734 | 1.0 | 2.1 | 40 |
| gpt-6-luna | flex | Σ-n-0 | base | 2 | 1760 | 44202 | 0 | 1.594 | 1.594 | 3.234 | 25.0 | 48.9 | 43 |

## persistgym_r12_exp1_cells

| model | tier_served | harness_cell | variant | n_runs | n_records | n_calls | n_calls_gate_waited | median_s_per_call | median_s_per_call_runs_gate_held_none | p90_s_per_call | median_calls_per_record | median_model_s_per_record | output_tokens_per_call |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | standard | W-n-0 | base | 4 | 200 | 4812 | 0 | 1.125 | 1.125 | 2.0 | 24.0 | 31.1 | 103 |
| claude-haiku-5-5 | standard | W-nd-0 | base | 4 | 200 | 4812 | 0 | 1.375 | 1.375 | 2.781 | 24.0 | 38.1 | 209 |
| claude-haiku-5-5 | standard | W-np-0 | base | 4 | 200 | 4812 | 0 | 2.328 | 2.328 | 4.266 | 24.0 | 62.9 | 544 |
| claude-haiku-5-5 | standard | W-nx-0 | base | 4 | 200 | 4812 | 0 | 1.125 | 1.125 | 2.0 | 24.0 | 31.0 | 108 |

## persistgym_runs

| experiment | run_id | harness_cells | variants | tier_served | n_records | n_calls | calls_gate_waited | median_s_per_call | costs_row_latency_s | output_tokens_per_call |
|---|---|---|---|---|---|---|---|---|---|---|
| persistgym | 20261010T055742Z-F-0-gpt-6-luna | F-0 | base | flex | 1600 | 38456 | 0 | 1.687 | 1.687 | 23 |
| persistgym | 20261010T073840Z-W-0-gpt-6-luna | W-0 | base | flex | 1600 | 38867 | 0 | 1.359 | 1.359 | 30 |
| persistgym | 20261010T084438Z-W-n-0-gpt-6-luna | W-n-0 | base | flex | 1600 | 38823 | 0 | 1.656 | 1.656 | 38 |
| persistgym | 20261010T100804Z-sigma-n-0-gpt-6-luna | Σ-n-0 | base | flex | 1600 | 40224 | 0 | 1.61 | 1.61 | 43 |
| persistgym | 20261010T113553Z-F-0-gpt-6-luna | F-0 | restated | flex | 1600 | 38476 | 0 | 1.625 | 1.625 | 23 |
| persistgym | 20261010T125241Z-single-turn-gpt-6-luna | single-turn | base | flex | 800 | 800 | 0 | 2.094 | 2.094 | 40 |
| persistgym | 20261010T125444Z-F-0-gpt-6-luna-repeat1 | F-0 | base | flex | 160 | 3803 | 0 | 1.625 | 1.625 | 24 |
| persistgym | 20261010T130303Z-W-0-gpt-6-luna-repeat1 | W-0 | base | flex | 160 | 3844 | 0 | 1.594 | 1.594 | 31 |
| persistgym | 20261010T131136Z-W-n-0-gpt-6-luna-repeat1 | W-n-0 | base | flex | 160 | 3835 | 0 | 1.562 | 1.562 | 38 |
| persistgym | 20261010T132132Z-sigma-n-0-gpt-6-luna-repeat1 | Σ-n-0 | base | flex | 160 | 3978 | 0 | 1.422 | 1.422 | 43 |
| persistgym | 20261010T133022Z-F-0-gpt-6-luna-repeat1 | F-0 | restated | flex | 160 | 3805 | 0 | 1.422 | 1.422 | 23 |
| persistgym | 20261010T133738Z-single-turn-gpt-6-luna-repeat1 | single-turn | base | flex | 80 | 80 | 0 | 1.625 | 1.625 | 40 |
| persistgym | 20261010T202127Z-F-0-gpt-6-luna | F-0 | base | flex | 8 | 216 |  | 1.648 | 1.649 | 23 |
| persistgym_haiku | 20261018T141157Z-F-0-claude-haiku-5-5 | F-0 | base | standard | 1600 | 38467 | 0 | 0.766 | 0.766 | 48 |
| persistgym_haiku | 20261018T144829Z-W-0-claude-haiku-5-5 | W-0 | base | standard | 1034 | 24971 | 0 | 0.906 | 0.906 | 54 |
| persistgym_haiku | 20261018T154817Z-W-0-claude-haiku-5-5 | W-0 | base | standard | 8 | 178 | 40 | 0.829 | 0.813 | 41 |
| persistgym_haiku | 20261018T154918Z-W-0-claude-haiku-5-5 | W-0 | base | standard | 584 | 14213 | 0 | 0.875 | 0.875 | 54 |
| persistgym_haiku | 20261018T162133Z-F-0-claude-haiku-5-5 | F-0 | restated | standard | 1600 | 38462 | 0 | 0.766 | 0.766 | 46 |
| persistgym_haiku | 20261018T165717Z-single-turn-claude-haiku-5-5 | single-turn | base | standard | 354 | 354 | 0 | 1.429 | 1.429 | 120 |
| persistgym_haiku | 20261018T225735Z-single-turn-claude-haiku-5-5 | single-turn | base | standard | 4 | 4 | 0 | 1.5 | 1.5 | 117 |
| persistgym_haiku | 20261018T225747Z-single-turn-claude-haiku-5-5 | single-turn | base | standard | 4 | 4 | 0 | 1.516 | 1.516 | 133 |
| persistgym_haiku | 20261018T225838Z-single-turn-claude-haiku-5-5 | single-turn | base | standard | 444 | 444 | 0 | 1.438 | 1.438 | 118 |
| persistgym_haiku | 20261018T230235Z-F-0-claude-haiku-5-5-repeat1 | F-0 | base | standard | 160 | 3800 | 1475 | 0.844 | 0.765 | 49 |
| persistgym_haiku | 20261018T230709Z-W-0-claude-haiku-5-5-repeat1 | W-0 | base | standard | 160 | 3840 | 0 | 0.844 | 0.844 | 55 |
| persistgym_haiku | 20261018T231530Z-F-0-claude-haiku-5-5-repeat1 | F-0 | restated | standard | 160 | 3800 | 1481 | 0.828 | 0.75 | 46 |
| persistgym_haiku | 20261018T231953Z-single-turn-claude-haiku-5-5-repeat1 | single-turn | base | standard | 80 | 80 | 0 | 1.469 | 1.469 | 115 |
| persistgym_haiku_notes | 20261024T060051Z-W-n-0-claude-haiku-5-5 | W-n-0 | base | standard | 1600 | 38857 | 0 | 0.938 | 0.938 | 88 |
| persistgym_haiku_provenance | 20261101T184553Z-W-np-0-claude-haiku-5-5 | W-np-0 | base | standard | 29 | 618 | 0 | 2.149 | 2.141 | 508 |
| persistgym_haiku_provenance | 20261101T190445Z-W-np-0-claude-haiku-5-5 | W-np-0 | base | standard | 784 | 18940 | 0 | 2.141 | 2.141 | 558 |
| persistgym_haiku_provenance | 20261102T002751Z-W-npd-0-claude-haiku-5-5 | W-npd-0 | base | standard | 800 | 19300 | 0 | 2.179 | 2.172 | 533 |
| persistgym_haiku_control | 20261106T050520Z-W-n-0-claude-haiku-5-5 | W-n-0 | base | standard | 393 | 9440 | 17 | 0.969 | 0.969 | 109 |
| persistgym_haiku_r12_notes | 20261112T150644Z-W-n-0-claude-haiku-5-5 | W-n-0 | base | standard | 50 | 1242 | 0 | 1.157 | 1.156 | 105 |
| persistgym_haiku_r12_notes | 20261112T152127Z-W-np-0-claude-haiku-5-5 | W-np-0 | base | standard | 50 | 1242 | 0 | 2.484 | 2.484 | 578 |
| persistgym_haiku_r12_notes | 20261112T155022Z-W-nd-0-claude-haiku-5-5 | W-nd-0 | base | standard | 50 | 1242 | 0 | 1.422 | 1.422 | 207 |
| persistgym_haiku_r12_notes | 20261112T160838Z-W-nx-0-claude-haiku-5-5 | W-nx-0 | base | standard | 50 | 1242 | 0 | 1.172 | 1.172 | 113 |
| persistgym_haiku_r12_notes | 20261112T162328Z-W-np-0-claude-haiku-5-5 | W-np-0 | base | standard | 50 | 1182 | 0 | 2.406 | 2.406 | 575 |
| persistgym_haiku_r12_notes | 20261112T165047Z-W-nd-0-claude-haiku-5-5 | W-nd-0 | base | standard | 50 | 1182 | 0 | 1.313 | 1.313 | 186 |
| persistgym_haiku_r12_notes | 20261112T170658Z-W-nx-0-claude-haiku-5-5 | W-nx-0 | base | standard | 50 | 1182 | 0 | 1.062 | 1.062 | 107 |
| persistgym_haiku_r12_notes | 20261112T171952Z-W-n-0-claude-haiku-5-5 | W-n-0 | base | standard | 50 | 1182 | 0 | 1.109 | 1.109 | 103 |
| persistgym_haiku_r12_notes | 20261112T173336Z-W-nd-0-claude-haiku-5-5 | W-nd-0 | base | standard | 50 | 1188 | 0 | 1.484 | 1.484 | 244 |
| persistgym_haiku_r12_notes | 20261112T175138Z-W-nx-0-claude-haiku-5-5 | W-nx-0 | base | standard | 50 | 1188 | 0 | 1.172 | 1.172 | 108 |
| persistgym_haiku_r12_notes | 20261112T180539Z-W-n-0-claude-haiku-5-5 | W-n-0 | base | standard | 50 | 1188 | 0 | 1.094 | 1.094 | 99 |
| persistgym_haiku_r12_notes | 20261112T181844Z-W-np-0-claude-haiku-5-5 | W-np-0 | base | standard | 50 | 1188 | 0 | 2.141 | 2.141 | 506 |
| persistgym_haiku_r12_notes | 20261112T184402Z-W-nx-0-claude-haiku-5-5 | W-nx-0 | base | standard | 50 | 1200 | 0 | 1.11 | 1.11 | 103 |
| persistgym_haiku_r12_notes | 20261112T185728Z-W-n-0-claude-haiku-5-5 | W-n-0 | base | standard | 50 | 1200 | 0 | 1.125 | 1.125 | 103 |
| persistgym_haiku_r12_notes | 20261112T191112Z-W-np-0-claude-haiku-5-5 | W-np-0 | base | standard | 50 | 1200 | 0 | 2.25 | 2.25 | 518 |
| persistgym_haiku_r12_notes | 20261112T193815Z-W-nd-0-claude-haiku-5-5 | W-nd-0 | base | standard | 50 | 1200 | 0 | 1.281 | 1.281 | 199 |
| persistgym_sonnet_r12 | 20261112T195445Z-W-n-0-claude-sonnet-5-5 | W-n-0 | base | standard | 50 | 1242 | 0 | 2.281 | 2.281 | 317 |
| persistgym_sonnet_r12 | 20261112T202234Z-W-np-0-claude-sonnet-5-5 | W-np-0 | base | standard | 50 | 1242 | 0 | 3.063 | 3.063 | 488 |
| persistgym_sonnet_r12 | 20261112T205954Z-F-0-claude-sonnet-5-5 | F-0 | base | standard | 7 | 178 |  | 1.539 | 1.539 | 44 |
| persistgym_sonnet_r12 | 20261112T222631Z-F-0-claude-sonnet-5-5 | F-0 | base | standard | 44 | 1086 | 0 | 1.563 | 1.563 | 51 |
| persistgym_haiku_r12_block | 20261112T235047Z-W-b-0-claude-haiku-5-5 | W-b-0 | base | standard | 400 | 9796 | 0 | 0.937 | 0.937 | 53 |
| persistgym_haiku_r12_block | 20261113T011523Z-W-b-0-claude-haiku-5-5 | W-b-0 | base | standard | 400 | 9549 | 0 | 0.922 | 0.922 | 52 |
| persistgym_haiku_r12_block | 20261113T023608Z-W-b-0-claude-haiku-5-5 | W-b-0 | base | standard | 400 | 9796 | 0 | 0.922 | 0.922 | 52 |
| persistgym_haiku_r12_block | 20261113T035847Z-W-b-0-claude-haiku-5-5 | W-b-0 | base | standard | 400 | 9717 | 0 | 0.937 | 0.937 | 54 |
