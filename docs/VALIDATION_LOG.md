# Validation log

Owner: **Validator (V)**, per `CLAUDE.md`. This file records what V has reproduced independently: the exact commands, the observed values, and pass or fail. Fill the rows **only from output you ran yourself**, and note the commit hash on every row. Expected values below were checked once on `591d490` (Windows 11, Python 3.12) when this file was started. They are what you should see, not a substitute for running the commands.

How to use it: run each step, paste the observed value, and set Status to `PASS`, `FAIL` (open an issue for the owner) or `N/A`.

---

## Continuation record — 2026-11-15

`docs/VALIDATOR_HANDOFF.md` did not exist when this pass began, so it has been created from the repository state. The complete machine-readable Experiment A artifact and the human-readable summary are now independently validated at commit `f2a03e6`; see that handoff for the code-level reconciliation.

| Check | Exact command | Observed | Status | Commit |
| --- | --- | --- | --- | --- |
| Focused JSON/dashboard validation | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/dashboard/test_experiment_json.py tests/unit/dashboard/test_dashboard_data.py tests/unit/dashboard/test_dashboard_app.py` | `25 passed in 2.70s` | PASS | `f2a03e6` |
| Full suite | `.venv/bin/python -m pytest -q -p no:cacheprovider` | `337 passed in 18.86s` | PASS | `f2a03e6` |
| Frozen Experiment A artifact generation | `.venv/bin/python scripts/run_experiment_a.py` | completed in 16.1 s; `experiment_a.json`, `experiment_a_summary.json`, and CSV written | PASS | `f2a03e6` |
| Full artifact deserialization | `samg.dashboard.data.load_experiment_result(artifacts/experiments/experiment_a.json)` | 960 records; policies `P0-H/P0-F/P0-D/P1/P2/P3`; 3 comparisons; five 120-value training series | PASS | `f2a03e6` |
| Dashboard aggregate rendering | `streamlit.testing.v1.AppTest` against `src/samg/dashboard/app.py` | no exceptions/errors; default selection `experiment_a.json`; four dataframes and one Plotly learning curve | PASS | `f2a03e6` |
| Missing, malformed, legacy-summary, and incompatible JSON | covered by `test_experiment_json.py` above | all guarded-error tests passed | PASS | `f2a03e6` |
| Repeat frozen Experiment A | `.venv/bin/python scripts/run_experiment_a.py --out artifacts/validation/run2` plus `sha256sum` | both full JSON artifacts: `6df9ade8d5020387dde73d064fda55a96a1d000809b102c8f7b7610a3dfa3b9c` | PASS | `f2a03e6` |

**Reproducibility finding (open, owner A):** the identical current-environment reruns agree byte-for-byte, but differ from the historical figures in `docs/RESULTS.md` despite the same frozen config hash `8b98c35a16a6d069`. Fresh P3−P1 is `−0.005894` (CI `[−0.009153, −0.003071]`) rather than `−0.00130` (CI `[−0.00332, +0.00046]`); fresh P3−P2 is `+0.001776` (CI `[+0.000714, +0.002956]`) rather than `+0.00629` (CI `[+0.00377, +0.00898]`). This pass uses Linux / Python 3.14.8 / OR-Tools 9.15.6755; the historical validation header says Python 3.12. No frozen configuration, seed, implementation, or published result was changed by V.

Working tree check at the end of this milestone: `Temp_TASK.md` remains the only pre-existing user modification; validator documentation changes are intentional. Artifacts and `.venv` are ignored.

### Continued validation — demo, security, fixtures, and decisions

| Check | Exact command / method | Observed | Status | Commit |
| --- | --- | --- | --- | --- |
| Contract + integration | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/contract tests/integration` | `68 passed in 5.79s` | PASS | `f2a03e6` |
| Assurance + persistence | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/assurance tests/unit/persistence` | `37 passed in 0.99s`; assertions inspected for signature, role, freshness, state, append-only DB, durable replay and duplicate learning events | PASS | `f2a03e6` |
| CLI demo | standard and `--greedy` twice; protected `run` seeds 1/2/3 twice | every paired output byte-identical; demo showed no host-time output | PASS | `f2a03e6` |
| Experiment C | `.venv/bin/python scripts/run_experiment_c.py --out artifacts/validation/experiment_c --doc /tmp/samg-results-security-validation.md` | attack hash `173ba5ea83c04bea`; protected unsupported admissions 0 at every level; S1 diverges; no-evidence and replay controls pass | PASS | `f2a03e6` |
| Judge scenario | `judge_scenario()` count and IDs | 6 agents A0–A5; 8 tasks T1–T8; 7 dependencies | PASS | `f2a03e6` |
| Contract reachability fixture | parsed `01_reachable_mission.json` | 2 agents, 2 tasks, 1 dependency; distinct from the runtime judge scenario | PASS (clarified) | `f2a03e6` |
| Decision audit | inspected D009–D018 and superseding D020/D030–D037 | all required entries present | PASS | `f2a03e6` |
| Full three-tab dashboard acceptance | `AppTest` live Mission Control + topology comparison, saved Adaptive Evaluation Lab, live Security attack, reset | no exceptions/errors; 14 mission dataframes/3 charts, 15/6 after comparison, 20/7 after attack; reset seed returned to 7; full artifact selected | PASS | `f2a03e6` |

---

## 1. Environment

| Date | Commit | OS | Python | Install method | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-11-15 | `f2a03e6` | Linux 7.3.1-1-cachyos x86_64 | 3.14.8 | `.venv/bin/python -m pip install -e '.[dev]'` | First sandboxed dependency install could not resolve PyPI; approved retry completed successfully. |

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
| Install finishes without errors | no errors | finished successfully | PASS | `f2a03e6` |
| `import samg.domain` | prints `ok` | installed package imports through focused and full test suites | PASS | `f2a03e6` |

## 3. Test suite

```text
.venv\Scripts\python -m pytest -q -p no:cacheprovider     (Windows)
.venv/bin/python -m pytest -q -p no:cacheprovider         (POSIX)
```

| Check | Expected at `591d490` | Observed | Status | Commit |
| --- | --- | --- | --- | --- |
| Pass/fail count | `298 passed`, 0 failed, 0 skipped (about 100 s) | `337 passed in 18.86s`, 0 failed, 0 skipped | PASS | `f2a03e6` |
| Contract tests only: `pytest -q tests/contract` | all pass | combined contract + integration command: `68 passed in 5.79s` | PASS | `f2a03e6` |
| Vertical slice only: `pytest -q tests/integration` | all pass | combined contract + integration command: `68 passed in 5.79s` | PASS | `f2a03e6` |

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
| `demo` twice → identical | `fc`: "no differences encountered"; `diff`: no output | SHA-256 both `818530ffc087689b6e0870ec134f3ca50a33831c29bfbc0b6ecd54edc4c70c57`; `cmp` exit 0 | PASS | `f2a03e6` |
| `demo --greedy` twice → identical | identical | SHA-256 both `7620a877d584e0dd091f5901a4a30518b8c0c0912e017c93db18d68581ee188c`; `cmp` exit 0 | PASS | `f2a03e6` |
| `run --seed 1` twice → identical | identical | SHA-256 both `6c14f4394a40a065d0db0e12efec591bafba908a72cdd8aeda1cd8723d85d153`; `cmp` exit 0 | PASS | `f2a03e6` |
| `run --seed 2` twice → identical | identical | SHA-256 both `0cea2b3f416a0b8b9478846a2eacf2b4d7cb27928c002b6f549fe6436c314201`; `cmp` exit 0 | PASS | `f2a03e6` |
| `run --seed 3` twice → identical | identical | SHA-256 both `2a9841c9640e39f15a8fea2ef638ee18db4f289c1207ac174b9c973f003f29ae`; `cmp` exit 0 | PASS | `f2a03e6` |
| Demo prints no wall-clock values | no runtimes or timestamps from the host clock | no `runtime`, `wall-clock`, `timestamp`, `time:`, or `elapsed` match in the captured output | PASS | `f2a03e6` |

## 5. Hand-check values

Compute each value **by hand** (or in a spreadsheet) first. Then compare with the code or the demo output.

Parameters (`config/topology_costs.yaml`, `config/reward.yaml`): `h0 = 1.0`, `h1 = 0.5`, `link_cost = 0.25`, `max_path_hops = 4`, `handoff_delay_ms_per_hop = 120000`, reward weights `0.65 / 0.15 / 0.10 / 0.10`.

| # | Quantity | Hand formula | Expected | Where to compare | Observed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | Judge-mission dependency density `d` | 8 tasks, 7 edges (T1→…→T8); `7 / (8·7/2) = 7/28` | **0.25** | demo Section 1 `[1]` `dependency_density=0.250` | `0.250`; helper returned `0.25` | PASS |
| H2 | Handoff cost, 2 hops (HIERARCHICAL, two non-hub agents through A0) | `h0 + 2·h1 = 1.0 + 1.0` | **2.0** | demo `[6]` rows `hops=2 cost=2.00` | `2.00`; helper returned `2.0` | PASS |
| H3 | Handoff delay, 2 hops | `2 × 120000 ms` | **240000 ms** (4 min) | demo `[6]` `delay=4 min` | `4 min` | PASS |
| H4 | Coordination normaliser, judge mission | `7·(h0 + 4·h1) + 0.25·(6·5/2) = 21 + 3.75` | **24.75** | `max_coordination_cost(7, 6, costs)` | helper returned `24.75` | PASS |
| H5 | `H` for demo Section 1 (4 handoffs × 2.0, 5 links) | `(8.00 + 0.25·5) / 24.75 = 9.25 / 24.75` | **0.374** | demo `[9]` `H= 0.374` | `0.374` | PASS |
| H6 | Reward, all best (C=1, T=R=H=0) | `0.65 + 0.15 + 0.10 + 0.10` | **1.0** | `compute_reward` | helper returned `1.0` | PASS |
| H7 | Reward, all worst (C=0, T=R=H=1) | `0` | **0.0** | `compute_reward` | helper returned `0.0` | PASS |
| H8 | Reward, mixed (C=1, T=R=H=0.5) | `0.65 + 0.15·0.5 + 0.10·0.5 + 0.10·0.5` | **0.825** | `compute_reward` | helper returned `0.8250000000000001` | PASS |
| H9 | Reward, demo Section 1 | `0.65·1 + 0.15·(1−0.718) + 0.10·(1−0.735) + 0.10·(1−0.374)` | **0.7814** | demo `[9]` `reward r = 0.7814` | `0.7814` | PASS |
| H10 | Allocation objective, demo Section 1 | `1.0·241.0 + 10·8.00 + 0.25·105.0` | **347.25** | demo `[5]` `weighted_total=347.25` | `347.25` | PASS |
| H11 | LinUCB after one update (`d=5`, `λ=1`, x = demo context, r = 0.7814) | `θ = (I + xxᵀ)⁻¹ r x` | **[0.184, 0.046, 0.176, 0.096, 0.184]** | demo `[10]` `theta[HIERARCHICAL]` | NumPy and demo both `[0.184, 0.046, 0.176, 0.096, 0.184]` | PASS |
| H12 | Handoff cost per topology for one fixed assignment (THREE_PERSON_PLAN §4, V step 1) | `h0 + h1·hops` per handoff | H=8.0; F=9.5; D=6.5 | `HopTable` over `A3→A4`, `A4→A3`, `A3→A4`, `A4→A2` | H `8.0`, F `9.5`, D `6.5` | PASS |

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
| False claims corroborated by the ACP (S2) | `false claims submitted 10, corroborated 0` | `10` submitted, `0` corroborated | PASS | `f2a03e6` |
| Honest claims blocked (false rejections) | `0/177` | `0/177` | PASS | `f2a03e6` |
| S1 updates from attacker-claimed reward | `10/10` | `10/10` | PASS | `f2a03e6` |
| Picks of attacker-preferred FUNC: S2 / S1 | `0/10` / `7/10` | `0/10` / `7/10` | PASS | `f2a03e6` |
| Replay | `DUPLICATE DUPLICATE_EVENT_ID; re-offered episode -> refused DUPLICATE_EPISODE; state unchanged: True` for both | exact expected text for S1 and S2 | PASS | `f2a03e6` |
| Section 1 persistence | `private keys stored = 0`; `learning updates applied = 1` | exact expected values | PASS | `f2a03e6` |
| `learning_events` applied rows = ADMITTED episodes | equal | demo Section 1: one ADMITTED episode and one applied learning event; `test_learning_events_applied_once_per_instance` also passed | PASS | `f2a03e6` |
| A duplicate dedupe key insert fails | an error, not a second row | `test_duplicate_dedupe_key_rejected_by_db` passed (both duplicate sequence and duplicate ID raise `DuplicateRecord`) | PASS | `f2a03e6` |

The demo's attack is an illustration, not Experiment C. Record the Experiment C numbers in §7 once item 15 lands.

## 7. Experiment results (copy only from runner output)

Fill these only from runner CSV/JSON output (THREE_PERSON_PLAN §6, V steps 1–4). Note the run ID and the config hash of the frozen `config/experiment.yaml`.

| Check | Expected | Observed | Status | Run ID / commit |
| --- | --- | --- | --- | --- |
| dev ∩ train ∩ test seed sets pairwise empty | empty | `test_splits_are_disjoint_and_hold_out_combos_only_at_test` passed within full suite | PASS | `f2a03e6` |
| Frozen config hash in results = hash of `config/experiment.yaml` | equal | artifact and committed config both `8b98c35a16a6d069` | PASS | `f2a03e6` |
| Experiment A: P3 vs P1 (mean, 95 % CI, n) | measured | `−0.005894`, `[−0.009153, −0.003071]`, n=54; differs from historical `RESULTS.md` (documented above) | PASS (fresh run) | `f2a03e6` |
| Experiment B: P3 vs P2 (mean, 95 % CI, n) | measured | `+0.001776`, `[+0.000714, +0.002956]`, n=60; differs from historical `RESULTS.md` (documented above) | PASS (fresh run) | `f2a03e6` |
| Infeasibility rate per topology | reported | P0-H `0/60`; P0-F `0/60`; P0-D and P1 `0/54`, with D unavailable on 6/60; P2 and P3 `0/60` | PASS | `f2a03e6` |
| Experiment C: S2 admitted unsupported reports | 0 | `0/6` at 20%; `0/12` at 40%; zero manipulated updates; reference state byte-identical | PASS | `f2a03e6` |
| Experiment C: S1 divergence ‖θ_S1 − θ_S2‖ | > 0 | at 40%, max S1 vs S2 θ L2 `0.077`; 26/30 follow-up selections changed vs reference | PASS | `f2a03e6` |
| Experiment C: FRR with denominator | reported | S2 `0/538`, `0/537`, `0/534` at 0/20/40%; aggregate `0/1609` | PASS | `f2a03e6` |
| §12.10 falsification checklist done (supported / not supported / parameter-sensitive) | done | A/B current-environment rerun does not reproduce historical values; security renderer records supported gate and state-shift claims, unsupported utility-harm claim | PASS (recorded) | `f2a03e6` |

## 8. Merge log (pytest after every merge to `main`)

| Date | Commit | Passed | Failed | Skipped | Demo identical? | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-15 | `f2a03e6` | 337 | 0 | 0 | yes (standard and greedy) | Full suite after JSON-artifact change; standard/greedy demos plus seed 1–3 single missions all byte-identical. |

## 9. Invariant trace table (THREE_PERSON_PLAN §5, V step 3)

Map each brief §8.9 invariant to the test that proves it. Any invariant without a test goes back to Dev B as an issue.

| Invariant | Statement (from brief §8.9) | Proving test (file::test) | Status |
| --- | --- | --- | --- |
| INV-01 | Exact brief wording unavailable in this repository | brief §8.9 required to map accurately | BLOCKED: do not invent requirement |
| INV-02 | Exact brief wording unavailable in this repository | brief §8.9 required to map accurately | BLOCKED: do not invent requirement |
| INV-03 | Exact brief wording unavailable in this repository | brief §8.9 required to map accurately | BLOCKED: do not invent requirement |
| INV-04 | Exact brief wording unavailable in this repository | brief §8.9 required to map accurately | BLOCKED: do not invent requirement |
| INV-05 | Only ADMITTED episodes with an ACP-recomputed reward update protected policy | `tests/integration/test_experiment_a.py::test_learning_only_from_admitted_and_ground_truth_kept_separate`; `tests/unit/test_evaluation.py::test_learners_update_only_from_admitted_and_never_at_test` | PASS |
| INV-06 | Exact brief wording unavailable in this repository | brief §8.9 required to map accurately | BLOCKED: do not invent requirement |
| INV-07 | Exact brief wording unavailable in this repository | brief §8.9 required to map accurately | BLOCKED: do not invent requirement |
| INV-08 | At most one update per episode, also across restarts | `tests/unit/persistence/test_repositories.py::test_learning_events_applied_once_per_instance`; `::test_restart_keeps_replay_protection` | PASS |
| INV-09 | Exact brief wording unavailable in this repository | brief §8.9 required to map accurately | BLOCKED: do not invent requirement |
