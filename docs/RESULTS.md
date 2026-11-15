# Experiments A/B — measured results

**Summary.** On 60 paired held-out missions, LinUCB (P3) does **not** beat the best fixed topology
(P1 = always distributed): −0.0013 reward, 95% CI [−0.0033, +0.0005]. P3 beats context-free UCB1 (P2) by +0.0063,
CI [+0.0038, +0.0090], but only because UCB1 locked onto the worst arm. Under the predeclared ablations the
P3 > P2 gap disappears, and P3 is significantly *worse* than P1 in 7 of 10 settings. All topologies complete every
mission, and the reward gaps are below 0.01.

### P4 follow-up comparison

Contextual epsilon-greedy (P4) is implemented as a separate follow-up comparison.
Its dev-tuning and held-out workflow is `scripts/run_experiment_epsilon_greedy.py`,
with its own `config/epsilon_greedy.yaml` and config hash. No held-out P4 result is
recorded in the original P0-P3 experiment; the P0-P3 measurements below remain
unchanged. The P4 follow-up used the existing 40/120/60 dev/train/test split,
epsilon candidates `{0.05, 0.1, 0.2, 0.3, 0.5}`, and five policy seeds
`101, 211, 307, 401, 503`. The selected epsilon was 0.05. Its follow-up config
hash is `e74de5917e5e0dde`.

Dev evaluation means were 0.77158 (epsilon 0.05), 0.77135 (0.1), 0.77132
(0.2), 0.77140 (0.3), and 0.77109 (0.5); their 95% CIs overlap. The selected
value is weakly supported by dev data.

#### Held-out comparison

P4's reward is averaged across its five policy seeds per mission. Confidence
intervals are across the 60 paired held-out missions. P1 was selected as
DISTRIBUTED on training data; it and P0-D are N/A on six held-out missions.

| Policy | n | Mean reward | 95% CI | Mean regret | N/A |
|---|---:|---:|---|---:|---:|
| P0-H fixed hierarchical | 60 | 0.76828 | [0.76153, 0.77513] | 0.00677 | 0 |
| P0-F fixed functional-cell | 60 | 0.76554 | [0.75826, 0.77285] | 0.00951 | 0 |
| P0-D fixed distributed | 54 | 0.77319 | [0.76669, 0.78005] | 0.00206 | 6 |
| P1 best fixed (DISTRIBUTED) | 54 | 0.77319 | [0.76669, 0.78005] | 0.00206 | 6 |
| P2 UCB1 | 60 | 0.76554 | [0.75826, 0.77285] | 0.00951 | 0 |
| P3 LinUCB | 60 | 0.77183 | [0.76527, 0.77850] | 0.00322 | 0 |
| P4 contextual epsilon-greedy | 60 | 0.76618 | [0.75906, 0.77335] | 0.00887 | 0 |

| Paired comparison | P4 − baseline | 95% CI | W/L/T | Pairs |
|---|---:|---|---:|---:|
| P4 − P3 | −0.00565 | [−0.00827, −0.00327] | 15/39/6 | 60 |
| P4 − P2 | +0.00064 | [+0.00032, +0.00098] | 24/8/28 | 60 |
| P4 − P1 | −0.00719 | [−0.01046, −0.00443] | 15/39/0 | 54 |

P4 therefore beat this UCB1 run by a small margin, while trailing LinUCB and
best-fixed on the held-out set. P2 selected FUNCTIONAL_CELL on all 60 missions;
P4 selected FUNCTIONAL_CELL 229 times, HIERARCHICAL 68 times, and DISTRIBUTED
3 times across its 300 seed-by-mission decisions. It made 9 exploratory choices
(3% realized exploration rate). These results support a measured comparison on
this protocol, not a general claim that epsilon-greedy is superior.

The short `python -m samg demo` comparison remains illustrative only. Full
records and dev-tuning output are saved under the ignored
`artifacts/experiments/epsilon_greedy/` directory.

#### Full epsilon-grid sweep

To compare every predeclared epsilon value directly, the same held-out 60
missions were run for each value, with five independent P4 policy seeds per
epsilon. P0/P1/P2/P3 baselines were evaluated in that same run. The table gives
P4 mean reward across seeds and paired reward differences against LinUCB (P3),
UCB1 (P2), and best-fixed (P1). CIs are paired 95% bootstrap intervals;
win/loss/tie counts are relative to the named baseline. P1 has only 54 eligible
missions because DISTRIBUTED is unavailable on 6.

| ε | P4 reward (n=60) | P4−P3 [95% CI], W/L/T | P4−P2 [95% CI], W/L/T | P4−P1 [95% CI], W/L/T |
|---:|---:|---|---|---|
| 0.05 | 0.76618 | −0.00565 [−0.00827, −0.00327], 15/39/6 | +0.00064 [+0.00032, +0.00098], 24/8/28 | −0.00719 [−0.01046, −0.00443], 15/39/0 |
| 0.1 | 0.76803 | −0.00380 [−0.00596, −0.00189], 17/36/7 | +0.00249 [+0.00144, +0.00365], 36/11/13 | −0.00516 [−0.00789, −0.00272], 16/36/2 |
| 0.2 | 0.76756 | −0.00427 [−0.00669, −0.00211], 15/40/5 | +0.00202 [+0.00111, +0.00307], 31/13/16 | −0.00583 [−0.00884, −0.00324], 15/39/0 |
| 0.3 | 0.76804 | −0.00379 [−0.00601, −0.00191], 18/39/3 | +0.00250 [+0.00154, +0.00358], 39/13/8 | −0.00515 [−0.00787, −0.00281], 15/38/1 |
| 0.5 | 0.76979 | −0.00204 [−0.00402, −0.00038], 19/39/2 | +0.00425 [+0.00280, +0.00583], 45/13/2 | −0.00352 [−0.00585, −0.00160], 14/39/1 |

Across this epsilon grid, every P4 value trails LinUCB and best-fixed on this
test set (the paired intervals are below zero). Every value exceeds UCB1's
mean, but this reflects this particular UCB1 run's lock-in on FUNCTIONAL_CELL;
it does not establish a general epsilon-greedy advantage. ε=0.5 gives the
highest P4 mean here, while ε=0.05 remains the value selected by the separate
dev-only tuning rule. These results compare only the configured five values,
not every real number in [0,1]. Reproduce with
`python scripts/run_experiment_epsilon_greedy.py --all-epsilons`; raw records
are `epsilon_sweep_records.csv` and aggregate output is `epsilon_sweep_result.json`.

#### Headless policy-selection latency

I also measured decision latency separately from reward. The benchmark trained
P3 and each P4 epsilon/seed on the same 120 training missions through the real
runner and allocator/simulator/ACP feedback path, then timed only the real
`policy.select(context, eligible, schema)` call. Inputs came from the 60 held-out
scenarios; feature extraction, allocation, simulation, ACP, and frontend work
were outside the timed interval. After 500 warm-up calls, it measured 50 passes
over the 60 scenarios per policy. The benchmark uses `perf_counter_ns` and
interleaves policies. Machine: Windows 11, Intel64 Family 6 Model 170 Stepping
4, Python 3.12.10, NumPy 2.5.4.

| Policy | ε | Timed calls | Median | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| P3 LinUCB | — | 15,000 | 60.1 µs | 107.0 µs | 288.8 µs |
| P4 epsilon-greedy | 0.05 | 15,000 | 38.8 µs | 67.2 µs | 209.7 µs |
| P4 epsilon-greedy | 0.1 | 15,000 | 38.7 µs | 67.3 µs | 218.5 µs |
| P4 epsilon-greedy | 0.2 | 15,000 | 38.8 µs | 67.9 µs | 210.6 µs |
| P4 epsilon-greedy | 0.3 | 15,000 | 39.0 µs | 67.2 µs | 204.4 µs |
| P4 epsilon-greedy | 0.5 | 15,000 | 39.4 µs | 69.6 µs | 211.6 µs |

Both policies used the same five policy seeds, each trained on the same
120-mission stream. In this local microbenchmark, P4's median decision took
about 35% less time than P3's. That is a measured selector-only latency advantage in this specific
Python/hardware setup, not evidence of lower end-to-end mission latency: the
allocator, simulation, and orchestration are excluded and may dominate. The
P3 and P4 sample counts differ because P4 includes five policy seeds. Tail
latencies have noticeable host/runtime jitter, so these figures should be
treated as a local benchmark result, not a hardware-independent guarantee.
Reproduce with `python scripts/benchmark_policy_latency.py`; raw samples and
the machine/config manifest are in `policy_latency_samples.csv` and
`policy_latency_summary.json` under the ignored epsilon-greedy artifacts folder.

All numbers below come from one real run of `scripts/run_experiment_a.py` against the full pipeline
(CP-SAT allocation → simulator → witness → ACP admission), through `samg.evaluation.executor.OrchestrationExecutor`.
No value is estimated or copied from elsewhere. Raw output (gitignored): `artifacts/experiments/`
(`dev_tuning.json`, `experiment_a.json`, `experiment_a_records.csv`, `ablations.json`).

## Protocol as run

| Item | Value |
| --- | --- |
| Command | `.venv/Scripts/python scripts/run_experiment_a.py --ablations --ablation-train 90 --ablation-test 60` |
| Frozen config hash | `8b98c35a16a6d069` (experiment + topology_costs + allocation + reward), recorded in `config/experiment.yaml` |
| Missions | dev 40, train 120, **test 60** (60 paired held-out seeds; 9 of them use a held-out factor combination) |
| Sample sizes | Set from runtime only, before any result: the defaults (10/60/20) were raised to 40/120/60. Nothing was reduced. |
| Allocation | CP-SAT, `time_limit_s` 5, 1 worker, seed 0 (unchanged). No greedy fallback happened: every plan was feasible. |
| Cost model | `topo-cost-v1`: h0 1.0, h1 0.5, link_cost 0.25 (D021), span_overhead 0.10 (D031), distributed_max_degree 3 |
| Reward | `reward-v1`: 0.65 C + 0.15 (1−T) + 0.10 (1−R) + 0.10 (1−H) |
| Learners | P2 UCB1 c = 1.0. P3 LinUCB λ = 1.0, warm-up 2 per arm, seed 2026, **α = 1.0 (chosen on dev)** |
| Learning | P2 and P3 each made 120 updates, all from ADMITTED episodes. 0 updates were blocked: the witness is faithful and there is no attack in A/B. Learners were frozen at test. |
| Runtime | Main run (train + test) 31.2 s: allocation 20.1 s over 220 scenario solves, execution 18.0 s over 1 101 missions. Full script including ablations: 463 s. |

### Dev tuning (dev split only)

The α grid {0.1, 0.3, 0.5, 1.0} was declared before any run. The 40 dev missions were split into a 20-mission
learning stream and a 20-mission frozen evaluation block. Rule: highest dev-eval mean reward, with ties going to the
smaller α.

| α | n | Dev-eval mean | Std | 95% CI | Dev-eval selections |
| ---: | ---: | ---: | ---: | --- | --- |
| 0.1 | 20 | 0.7702 | 0.0267 | [0.7580, 0.7814] | H 20 |
| 0.3 | 20 | 0.7685 | 0.0261 | [0.7566, 0.7795] | H 6, F 14 |
| 0.5 | 20 | 0.7702 | 0.0267 | [0.7580, 0.7814] | H 20 |
| **1.0** | 20 | **0.7749** | 0.0256 | [0.7635, 0.7857] | D 18, H 1, F 1 |

The chosen α = 1.0 sits at the edge of the grid, and every dev confidence interval overlaps the others, so the choice
is weakly supported. After the freeze it was not revisited.

## Performance table (brief §12.11), held-out test

These are means over feasible runs (n). "Regret" is simulator-oracle regret: the best of the three fixed-topology
rewards on the same mission and seed, minus the reward of the selected arm (evaluation only, §12.3). "N/A" counts
missions where the policy's arm was not eligible (D030). Completion is the weighted completion C. Makespan is the
mean simulated minutes. Resource use is R. Planned handoff is the allocator's graph-derived handoff cost. Coordination
cost is the measured cost: handoffs plus D021 link maintenance.

| Policy | n | Mean reward | Std | 95% CI | Mean regret | Infeasible | N/A | Completion | Makespan (min) | Resource use | Planned handoff | Coordination cost |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| P0-H Fixed hierarchical | 60 | 0.7683 | 0.0267 | [0.7615, 0.7751] | 0.0068 | 0 | 0 | 1.000 | 194.0 | 0.754 | 8.90 | 10.08 |
| P0-F Fixed functional-cell | 60 | 0.7655 | 0.0290 | [0.7583, 0.7729] | 0.0095 | 0 | 0 | 1.000 | 197.2 | 0.752 | 9.27 | 10.45 |
| P0-D Fixed distributed | 54 | 0.7732 | 0.0255 | [0.7667, 0.7800] | 0.0021 | 0 | 6 | 1.000 | 193.6 | 0.751 | 6.19 | 7.12 |
| P1 Best fixed (training-selected = DISTRIBUTED) | 54 | 0.7732 | 0.0255 | [0.7667, 0.7800] | 0.0021 | 0 | 6 | 1.000 | 193.6 | 0.751 | 6.19 | 7.12 |
| P2 Context-free UCB | 60 | 0.7655 | 0.0290 | [0.7583, 0.7729] | 0.0095 | 0 | 0 | 1.000 | 197.2 | 0.752 | 9.27 | 10.45 |
| P3 LinUCB | 60 | 0.7718 | 0.0263 | [0.7653, 0.7785] | 0.0032 | 0 | 0 | 1.000 | 204.3 | 0.752 | 7.39 | 8.42 |

Simulator oracle (the best fixed arm per mission, evaluation only): mean 0.7751 over 60 missions. DISTRIBUTED is
best on 35 missions, HIERARCHICAL on 14, FUNCTIONAL_CELL on 6, and H and F tie on 5.

**Important caveat:** P1 and P0-D are not applicable on 6 test missions, where DISTRIBUTED has no feasible plan. Their
mean is over 54 missions, while P3's is over 60. The paired comparisons below use only matched missions. On those
6 missions, P3 picked H or F and averaged 0.7713, against 0.7732 for P0-H and an oracle of 0.7733.

### Paired comparisons (matched missions, same seeds; bootstrap 95% CI, seed 7)

| Comparison | Pairs | Mean diff | 95% CI | Wins / losses / ties |
| --- | ---: | ---: | --- | --- |
| **P3 − P1** (Experiment A) | 54 | −0.00130 | [−0.00332, 0.00046] | 4 / 6 / 44 |
| **P3 − P2** (Experiment B) | 60 | +0.00629 | [+0.00377, +0.00898] | 39 / 12 / 9 |
| P2 − P1 | 54 | −0.00770 | [−0.01103, −0.00485] | 14 / 40 / 0 |

### Selection frequencies at test, by family

| Policy | dependency_heavy (11) | loosely_coupled (11) | mixed (38) | Total |
| --- | --- | --- | --- | --- |
| P1 | D 10 (1 N/A) | D 11 | D 33 (5 N/A) | D 54 |
| P2 | F 11 | F 11 | F 38 | F 60 |
| P3 | D 10, H 1 | D 10, H 1 | D 24, H 11, F 3 | D 44, H 13, F 3 |

Mean test reward by family (n): P0-H 0.7734 (11) / 0.7469 (11) / 0.7730 (38); P0-F 0.7710 / 0.7410 / 0.7711;
P0-D = P1 0.7851 (10) / 0.7502 (11) / 0.7773 (33); P2 0.7710 / 0.7410 / 0.7711; P3 0.7800 (11) / 0.7507 (11) / 0.7756 (38).
On the 9 held-out-combination missions: P3 0.7709, P0-H 0.7690, P0-F 0.7652, P2 0.7652, and P0-D = P1 0.7698
(only 6 of the 9 have a distributed plan).

P2 (UCB1) settled on FUNCTIONAL_CELL, the worst fixed arm on test. Its test results are therefore the same as P0-F's.

## Falsification checklist (brief §12.10)

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| P3 beats P1 on held-out missions | **Not supported** | P3 − P1 = −0.0013, 95% CI [−0.0033, +0.0005], 54 pairs, 4 W / 6 L / 44 T. Adaptive selection does **not** beat the best fixed topology (always distributed). Do not claim it does. |
| P3 beats P2 (context adds value) | **Supported on the main test only; not robust** | P3 − P2 = +0.0063, CI [+0.0038, +0.0090], 60 pairs, 39 W / 12 L. The margin comes mostly from P2 locking onto FUNCTIONAL_CELL, the worst arm (P2 − P1 = −0.0077). This shows that UCB1 with c = 1 chose badly. It is weak evidence that the context features themselves are informative. On design-seed missions, where P2 finds the best arm, P3 − P2 = +0.0002 [−0.0017, +0.0021] (base). Do not claim that context adds value. |
| Advantage survives modest predeclared cost / reward-weight changes | **Parameter-sensitive** | P3 − P1 has no positive CI in any of 10 ablation settings and is significantly negative in 7 (e.g. span 0.05: −0.0089 [−0.0112, −0.0067]; efficiency-heavy weights: −0.0129 [−0.0181, −0.0078]). P3 − P2 is positive on the main test but +0.0002 [−0.0017, +0.0021] on the base design-seed set, and negative in 7/10 settings. |
| Graph is functional, not decorative | **Supported** | Measured coordination cost differs between topologies on 60/60 test missions, and makespan on 53/60. Fixed-arm mean coordination cost: H 10.08, F 10.45, D 7.12. The oracle-best topology varies (D 35, H 14, F 6, H=F tie 5). The topology-cost-zero ablation changes the rankings (below). One limit: H and F give identical reward on 30/60 missions, so the functional-cell builder often reduces to the hierarchical one. |
| Security criteria (S1/S2, FRR, witness trust) | Not covered here | Experiment C is out of scope for this document. |

## Sensitivity / ablations (brief §12.9)

Each setting reruns the complete A/B protocol through the real pipeline, with α = 1.0 and every other frozen
hyperparameter unchanged (nothing retuned). It uses its own **design-seed** missions: 90 train and 60 test, with seeds
from 60 000, disjoint from every dev/train/test seed, cycling through the full factor grid. P1 is re-selected on
each setting's training data. One setting changes per row, against the frozen base. "P3 − P1" and "P3 − P2" are paired
over matched missions (bootstrap 95% CI). The held-out test split was **not** used for any ablation.

| Setting | P1 (train-selected) | P1 mean | P2 mean | P3 mean | P3 − P1 [95% CI] (pairs; W/L) | P3 − P2 [95% CI] | P3 test selections | P3 regret | P1 regret |
|---|---|---:|---:|---:|---|---|---|---:|---:|
| base (frozen config) | D | 0.7734 | 0.7719 | 0.7721 | +0.00001 [−0.00207, +0.00208] (56; 10/9) | +0.00023 [−0.00168, +0.00205] | D 37, H 20, F 3 | 0.0027 | 0.0029 |
| topology cost zero (h0 = h1 = 0, no hop delay) | H | 0.7823 | 0.7823 | 0.7841 | +0.00181 [−0.00265, +0.00623] (60; 9/12) | +0.00181 [−0.00265, +0.00623] | D 17, H 27, F 16 | 0.0072 | 0.0090 |
| h0/h1 low (0.5/0.25) | D | 0.7747 | 0.7732 | 0.7674 | −0.00649 [−0.01058, −0.00251] (56; 15/38) | −0.00585 [−0.00969, −0.00218] | H 43, F 14, D 3 | 0.0092 | 0.0033 |
| h0/h1 high (2.0/1.0) | D | 0.7722 | 0.7710 | 0.7714 | +0.00062 [−0.00039, +0.00179] (56; 5/3) | +0.00050 [−0.00046, +0.00153] | D 48, H 10, F 2 | 0.0028 | 0.0035 |
| link_cost 0 (D021 off) | D | 0.7715 | 0.7698 | 0.7659 | −0.00440 [−0.00705, −0.00192] (56; 13/37) | −0.00388 [−0.00634, −0.00164] | H 52, F 6, D 2 | 0.0063 | 0.0023 |
| span_overhead 0 | D | 0.7835 | 0.7816 | 0.7731 | −0.00903 [−0.01155, −0.00663] (56; 1/33) | −0.00849 [−0.01086, −0.00628] | H 30, D 22, F 8 | 0.0086 | 0.0002 |
| span_overhead 0.05 | D | 0.7786 | 0.7768 | 0.7687 | −0.00894 [−0.01118, −0.00671] (56; 0/39) | −0.00811 [−0.01039, −0.00593] | H 25, F 18, D 17 | 0.0089 | 0.0006 |
| span_overhead 0.10 | = base | | | | | | | | |
| span_overhead 0.20 | H | 0.7663 | 0.7663 | 0.7622 | −0.00404 [−0.00667, −0.00148] (60; 6/28) | −0.00404 [−0.00667, −0.00148] | F 30, D 19, H 11 | 0.0100 | 0.0060 |
| reward weights completion_heavy | D | 0.8402 | 0.8390 | 0.8352 | −0.00408 [−0.00573, −0.00244] (56; 6/33) | −0.00381 [−0.00529, −0.00231] | F 41, D 17, H 2 | 0.0057 | 0.0018 |
| reward weights efficiency_heavy | D | 0.7175 | 0.7160 | 0.7035 | −0.01288 [−0.01806, −0.00784] (56; 11/42) | −0.01242 [−0.01727, −0.00781] | F 37, H 20, D 3 | 0.0157 | 0.0035 |

On these design-seed missions, P2 settles on the train-selected best arm (D or H, with a fallback when D is not
eligible) in every setting. That differs from the main training stream, where P2 locked onto F.

Planned-reward landscape (no learning; design grid, stride 2, 108 missions; `landscape.default_settings`). Share of
missions where each topology is the best planned arm, and the mean best-minus-runner-up margin:

| Setting | D | H | F | Mean margin |
|---|---:|---:|---:|---:|
| low h0/h1 | 0.574 | 0.269 | 0.157 | 0.0082 |
| base | 0.565 | 0.278 | 0.157 | 0.0079 |
| high h0/h1 | 0.593 | 0.241 | 0.167 | 0.0078 |
| link_cost 0 | 0.648 | 0.204 | 0.148 | 0.0064 |
| handoff cost 0 | 0.361 | 0.287 | 0.352 | 0.0065 |

**Sensitivity verdict.** In 0 of 10 settings is P3 significantly better than P1: 3 CIs include 0 and 7 are
significantly negative. P3 ≥ P2 is also **not robust**. On the base design-seed set the difference is +0.0002
(CI [−0.0017, +0.0021]), and 7/10 settings are significantly negative. The main-test P3 > P2 result (+0.0063)
therefore depends on the training stream (P2's lock-in on F) and is **parameter- and sample-sensitive**. The
topology-cost-zero ablation changes P1 (D → H), P3's selections and the landscape shares (D 0.565 → 0.361). The
graph-derived cost pathway works.

## Notes and disclosures

- Results were not retuned after the test run. α was fixed by the dev rule above, and `config/experiment.yaml` was
  frozen (hash `8b98c35a16a6d069`) before `run_experiment_a` touched train or test missions. A unit test checks
  that the recorded hash still matches every hashed config.
- The effect sizes are tiny (≈0.001–0.008 reward) because all three topologies complete every mission (C = 1.000).
  Differences come only from T, R and H, which together carry 0.35 of the reward weight. This matches the design-seed
  landscape study (WORK_QUEUE R7/R8: mean margin ≈ 0.008).
- Not-applicable fixed policies receive no reward instead of a zero. Their N/A counts are reported separately (brief §12.8).
