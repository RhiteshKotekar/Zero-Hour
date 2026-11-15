# Validation log

Owner: **Validator (V)**, per `CLAUDE.md`. This file records what V has reproduced independently: the exact commands, the observed values, and pass or fail. Fill the rows **only from output you ran yourself**, and note the commit hash on every row. Expected values below were checked once on `591d490` (Windows 11, Python 3.12) when this file was started. They are what you should see, not a substitute for running the commands.

How to use it: run each step, paste the observed value, and set Status to `PASS`, `FAIL` (open an issue for the owner) or `N/A`.

---

## 1. Environment

| Date | Commit | OS | Python | Install method | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | | | |

`git rev-parse --short HEAD` gives the commit. `python --version` gives the Python version.

## 2. Install (clean venv)

Windows (PowerShell), from the repo root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install pydantic networkx numpy ortools pyyaml pytest hypothesis cryptography
.venv\Scripts\python -m pip install -e . --no-deps
.venv\Scripts\python -c "import samg, samg.domain; print('ok')"
```

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pydantic networkx numpy ortools pyyaml pytest hypothesis cryptography
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python -c "import samg, samg.domain; print('ok')"
```

| Check | Expected | Observed | Status | Commit |
| --- | --- | --- | --- | --- |
| Install finishes without errors | no errors | | | |
| `import samg.domain` | prints `ok` | | | |

## 3. Test suite

```text
.venv\Scripts\python -m pytest -q -p no:cacheprovider     (Windows)
.venv/bin/python -m pytest -q -p no:cacheprovider         (POSIX)
```

| Check | Expected at `591d490` | Observed | Status | Commit |
| --- | --- | --- | --- | --- |
| Pass/fail count | `298 passed`, 0 failed, 0 skipped (about 100 s) | | | |
| Contract tests only: `pytest -q tests/contract` | all pass | | | |
| Vertical slice only: `pytest -q tests/integration` | all pass | | | |

After every merge to `main`, add a row to the merge log in §8.

## 4. Demo determinism

Windows:

```powershell
.venv\Scripts\python -m samg demo > a.txt
.venv\Scripts\python -m samg demo > b.txt
fc a.txt b.txt
```

POSIX:

```bash
.venv/bin/python -m samg demo > a.txt
.venv/bin/python -m samg demo > b.txt
diff a.txt b.txt && echo IDENTICAL
```

Run the same check for single missions (THREE_PERSON_PLAN §5, V step 1), for seeds 1, 2 and 3:

```text
python -m samg run --seed 1 --policy linucb --mode protected > s1a.txt
python -m samg run --seed 1 --policy linucb --mode protected > s1b.txt     (then diff; repeat for 2 and 3)
```

| Check | Expected | Observed | Status | Commit |
| --- | --- | --- | --- | --- |
| `demo` twice → identical | `fc`: "no differences encountered"; `diff`: no output | | | |
| `demo --greedy` twice → identical | identical | | | |
| `run --seed 1` twice → identical | identical | | | |
| `run --seed 2` twice → identical | identical | | | |
| `run --seed 3` twice → identical | identical | | | |
| Demo prints no wall-clock values | no runtimes or timestamps from the host clock | | | |

## 5. Hand-check values

Compute each value **by hand** (or in a spreadsheet) first. Then compare with the code or the demo output.

Parameters (`config/topology_costs.yaml`, `config/reward.yaml`): `h0 = 1.0`, `h1 = 0.5`, `link_cost = 0.25`, `max_path_hops = 4`, `handoff_delay_ms_per_hop = 120000`, reward weights `0.65 / 0.15 / 0.10 / 0.10`.

| # | Quantity | Hand formula | Expected | Where to compare | Observed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | Judge-mission dependency density `d` | 8 tasks, 7 edges (T1→…→T8); `7 / (8·7/2) = 7/28` | **0.25** | demo Section 1 `[1]` `dependency_density=0.250` | | |
| H2 | Handoff cost, 2 hops (HIERARCHICAL, two non-hub agents through A0) | `h0 + 2·h1 = 1.0 + 1.0` | **2.0** | demo `[6]` rows `hops=2 cost=2.00` | | |
| H3 | Handoff delay, 2 hops | `2 × 120000 ms` | **240000 ms** (4 min) | demo `[6]` `delay=4 min` | | |
| H4 | Coordination normaliser, judge mission | `7·(h0 + 4·h1) + 0.25·(6·5/2) = 21 + 3.75` | **24.75** | `max_coordination_cost(7, 6, costs)` | | |
| H5 | `H` for demo Section 1 (4 handoffs × 2.0, 5 links) | `(8.00 + 0.25·5) / 24.75 = 9.25 / 24.75` | **0.374** | demo `[9]` `H= 0.374` | | |
| H6 | Reward, all best (C=1, T=R=H=0) | `0.65 + 0.15 + 0.10 + 0.10` | **1.0** | | | |
| H7 | Reward, all worst (C=0, T=R=H=1) | `0` | **0.0** | | | |
| H8 | Reward, mixed (C=1, T=R=H=0.5) | `0.65 + 0.15·0.5 + 0.10·0.5 + 0.10·0.5` | **0.825** | | | |
| H9 | Reward, demo Section 1 | `0.65·1 + 0.15·(1−0.718) + 0.10·(1−0.735) + 0.10·(1−0.374)` | **0.7814** | demo `[9]` `reward r = 0.7814` | | |
| H10 | Allocation objective, demo Section 1 | `1.0·241.0 + 10·8.00 + 0.25·105.0` | **347.25** | demo `[5]` `weighted_total=347.25` | | |
| H11 | LinUCB after one update (`d=5`, `λ=1`, x = demo context, r = 0.7814) | `θ = (I + xxᵀ)⁻¹ r x` | **[0.184, 0.046, 0.176, 0.096, 0.184]** | demo `[10]` `theta[HIERARCHICAL]` | | |
| H12 | Handoff cost per topology for one fixed assignment (THREE_PERSON_PLAN §4, V step 1) | `h0 + h1·hops` per handoff | (V to compute) | `tests/unit/test_topology.py` | | |

Reward formula: `r = clip01(0.65·C + 0.15·(1 − T) + 0.10·(1 − R) + 0.10·(1 − H))`. The term definitions are in D033 and `src/samg/simulation/reward.py`.

Cross-check script (run it only *after* the hand values):

```text
python -c "from samg.simulation.scenarios import judge_scenario as j; from samg.context import extract_features as f; print(f(j(7)).as_dict())"
python -c "from samg.domain import load_topology_costs as l; c=l(); print(c.handoff_cost(2))"
python -c "from samg.domain import load_topology_costs as l; from samg.topology import max_coordination_cost as m; print(m(7, 6, l()))"
python -c "import numpy as np; x=np.array([1,.25,.956,.521,1.]); print(np.linalg.solve(np.eye(5)+np.outer(x,x), .7814*x).round(3))"
```

## 6. Security and learning-gate checks (demo Section 3 and SQLite)

| Check | Expected at `591d490` (demo settings) | Observed | Status | Commit |
| --- | --- | --- | --- | --- |
| False claims corroborated by the ACP (S2) | `false claims submitted 10, corroborated 0` | | | |
| Honest claims blocked (false rejections) | `0/177` | | | |
| S1 updates from attacker-claimed reward | `10/10` | | | |
| Picks of attacker-preferred FUNC: S2 / S1 | `0/10` / `7/10` | | | |
| Replay | `DUPLICATE DUPLICATE_EVENT_ID; re-offered episode -> refused DUPLICATE_EPISODE; state unchanged: True` for both | | | |
| Section 1 persistence | `private keys stored = 0`; `learning updates applied = 1` | | | |
| `learning_events` applied rows = ADMITTED episodes | equal | | | |
| A duplicate dedupe key insert fails | an error, not a second row | | | |

The demo's attack is an illustration, not Experiment C. Record the Experiment C numbers in §7 once item 15 lands.

## 7. Experiment results (copy only from runner output)

Fill these only from runner CSV/JSON output (THREE_PERSON_PLAN §6, V steps 1–4). Note the run ID and the config hash of the frozen `config/experiment.yaml`.

| Check | Expected | Observed | Status | Run ID / commit |
| --- | --- | --- | --- | --- |
| dev ∩ train ∩ test seed sets pairwise empty | empty | | | |
| Frozen config hash in results = hash of `config/experiment.yaml` | equal | | | |
| Experiment A: P3 vs P1 (mean, 95 % CI, n) | measured | | | |
| Experiment B: P3 vs P2 (mean, 95 % CI, n) | measured | | | |
| Infeasibility rate per topology | reported | | | |
| Experiment C: S2 admitted unsupported reports | 0 | | | |
| Experiment C: S1 divergence ‖θ_S1 − θ_S2‖ | > 0 | | | |
| Experiment C: FRR with denominator | reported | | | |
| §12.10 falsification checklist done (supported / not supported / parameter-sensitive) | done | | | |

## 8. Merge log (pytest after every merge to `main`)

| Date | Commit | Passed | Failed | Skipped | Demo identical? | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |

## 9. Invariant trace table (THREE_PERSON_PLAN §5, V step 3)

Map each brief §8.9 invariant to the test that proves it. Any invariant without a test goes back to Dev B as an issue.

| Invariant | Statement (from brief §8.9) | Proving test (file::test) | Status |
| --- | --- | --- | --- |
| INV-01 | | | |
| INV-02 | | | |
| INV-03 | | | |
| INV-04 | | | |
| INV-05 | Only ADMITTED episodes with an ACP-recomputed reward update protected policy | | |
| INV-06 | | | |
| INV-07 | | | |
| INV-08 | At most one update per episode, also across restarts | | |
| INV-09 | | | |
