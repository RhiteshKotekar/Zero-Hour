# SAMG vertical-slice demo (CLI)

Branch `integration/demo`. This is the barebones Phase 2 vertical slice (`THREE_PERSON_PLAN.md` §5): one
mission goes through the whole loop, a short stream shows LinUCB learning, and the signed false-report
attack (brief §9.2) is run against a protected and a vulnerable learner side by side. It is a terminal
demo; the Streamlit views (D018) are described in the Dashboard section below.

## Setup

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install pydantic networkx numpy ortools pyyaml pytest hypothesis cryptography
.venv\Scripts\python -m pip install -e . --no-deps
```

No ML or torch is needed.

## Commands

| Command | What it shows | Time |
| --- | --- | --- |
| `.venv\Scripts\python -m samg demo` | All three sections below | ~10 s |
| `.venv\Scripts\python -m samg demo --greedy` | Same, with the greedy allocator instead of CP-SAT | faster |
| `.venv\Scripts\python -m samg demo --alpha 0.5 --n-learn 20 --n-attack 6` | Different demo settings | |
| `.venv\Scripts\python -m samg run --seed 7 --policy linucb --mode protected` | One judge mission, every step | ~1 s |
| `.venv\Scripts\python -m samg run --seed 7 --policy linucb --mode vulnerable --attack` | Same mission; A4 signs a false reward claim and `VulnerableLinUCB` learns it | ~1 s |
| `.venv\Scripts\python -m samg run --seed 3 --policy ucb1` | Other policies: `ucb1`, `fixed-h`, `fixed-f`, `fixed-d` | |
| `.venv\Scripts\python -m samg run --seed 11 --scenario generated` | A mission from the seeded generator instead of the judge mission | |

Options for `run`: `--compromised A4`, `--prefer FUNCTIONAL_CELL|HIERARCHICAL|DISTRIBUTED`, `--alpha`, `--greedy`.
`--mode vulnerable` works only with `--policy linucb` (Experiment C only, never the default).

**Determinism.** The output depends only on the seeds and configs. No wall-clock values are printed (the
solver runtime is left out of the display and the deterministic run record). To check:

```powershell
.venv\Scripts\python -m samg demo > a.txt; .venv\Scripts\python -m samg demo > b.txt; fc a.txt b.txt
```

## What each section shows

**Section 1: clean run** (judge mission `M-judge-001`, seed 7, fresh protected LinUCB)

1. Mission intake: agents (capabilities, capacity, budget, coordinator flags) and tasks (capabilities,
   duration, demand, priority, dependencies).
2. Context features `ctx-v1 = [1, d, h, r, a]`.
3. Topology eligibility per D030: buildable and allocatable, with reasons for any excluded arm.
4. LinUCB mean, bonus and score for every arm, and the choice (cold start = seeded warm-up order).
5. Coordination graph: links, coordinators, graph version.
6. CP-SAT assignment: planned and simulated start/end per task, plus the objective terms.
7. Handoffs: path, hops, cost `h0 + h1·hops` and delay for every cross-agent dependency.
8. Evidence: signed witness transitions and signed agent claims. Each claim is AUTHENTICATED, then
   CORROBORATED, DISPUTED or PROVISIONAL.
9. Episode decision and the reward the ACP recomputed from witness evidence: raw metric, normalised value,
   term, weight and contribution for C, T, R and H. The agent's claimed reward is shown but not used.
10. Guarded policy update: the arm, the reward source, and how `b` and `θ` changed.
11. SQLite row counts (append-only tables). No private keys are stored.

**Section 2: learning.** 30 generated missions (`generate_scenario`, seeds from 5000, factor combos cycled
over the full grid) go through the same protected learner. Each row shows the features, the offered arms,
the pick, the ACP reward and an evaluation-only counterfactual: every allocatable arm is shadow-run on the
same seed, giving the best arm and the regret. Shadow results never reach the learner. The summary
compares picks and mean regret in the first and second halves, the per-arm counterfactual mean, and the
learned `θ·x` for the judge context.

**Section 3: attack**

- The pre-attack state is the Section 2 learner. It is cloned into S2 (`LinUCBPolicy`, protected) and
  S1 (`VulnerableLinUCB`). The attacker is A4, a registered and authorised agent that signs with its real
  key and fresh sequence numbers. Its preferred topology, FUNCTIONAL_CELL, is fixed in advance.
- **3a. Anatomy:** the judge mission runs on throwaway clones. A4 abandons T7 (a simulator fault
  injection, so T7 really FAILED) but signs "T7 complete" and a false reward. Both claims pass
  signature, role and freshness checks (AUTHENTICATED). Both are then DISPUTED against the witness
  record (`EXECUTING -> FAILED`). The episode is still ADMITTED, because the witness covers every
  reward-critical task, with the false claims quarantined. S2 learns the witness-derived reward and S1
  learns the claim.
- **3b. Attack window:** 10 generated missions, all attacked (reward claim only). S1 and S2 run in
  separate SQLite worlds on the same scenarios and seeds. The table shows each pick, the ACP verdict on
  the false claim, what S2 learned, and the true, claimed and learned reward for S1. Below it are the
  counts: false claims submitted and corroborated (0), honest claims blocked (the false-rejection
  count), and picks of the preferred topology for S2 and for S1.
- **Replay** (brief §9.3): resubmitting the attacker's signed claim returns DUPLICATE. Re-offering the
  episode is refused with DUPLICATE_EPISODE, and neither learner's state changes.
- **Divergence:** ‖A_S1−A_S2‖, ‖b_S1−b_S2‖ and ‖θ_S1−θ_S2‖ per arm, plus each learner's next choice for
  the judge mission and for an unseen generated mission.

Sample of a real run (trimmed):

```text
3b. Attack window: 10 generated missions, every one attacked (reward claim only, no sabotage).
 #   S2 pick  false claim -> ACP      S2 learns   |  S1 pick  true r   claimed  S1 learns
 32   DIST     DISPUTED                0.7676      |  DIST     0.7676   0.4676   0.4676
 34   DIST     DISPUTED                0.7811      |  FUNC     0.7834   0.9834   0.9834
  S2: false claims submitted 10, corroborated 0, honest claims blocked 0/177; updates used ACP-recomputed reward only
  S1: updates from attacker-claimed reward 10/10
  picks of preferred FUNC: S2 0/10   S1 8/10
  next choice for the judge mission: S2 -> DISTRIBUTED   S1 -> FUNCTIONAL_CELL
```

## Complete vs minimal

| Piece | Module | Status |
| --- | --- | --- |
| Domain contracts, topology, features, CP-SAT/greedy allocation, D030 eligibility, scenario generator | Dev A | Complete (unchanged) |
| Identity, signatures, freshness, state machine, LinUCB/UCB1/fixed/Vulnerable, SQLite | Dev B | Complete (unchanged) |
| Simulator engine `simulation/engine.py` | Dev A-owned, **integration version** | Minimal: jitter, per-hop delay, seeded retransmission/loss, forced failures. No capacity drain or agent failure/reallocation |
| Reward `simulation/reward.py` | Dev A-owned, **integration version** | Brief §7.2 with the normalisations in D033 (proposed); alternative weight sets are selectable |
| Witness `witness/service.py`, reports `witness/reports.py` | Dev B-owned, **integration version** | Minimal and working |
| ACP `assurance/admission.py` | Dev B-owned, **integration version** | Event validation, corroboration and episode admission. No graph-patch validation (§8.3); GRAPH_PATCH claims stay PROVISIONAL |
| Attack `evaluation/attacks.py` | Dev B-owned, **integration version** | Deterministic schedule and inflate/deflate claims. Not the full Experiment C harness (no dev-seed tuning, FRR over clean missions or held-out metrics) |
| `orchestration.py`, `cli.py`, `demo.py`, `__main__.py` | Dev B-owned, **integration version** | Working. `execute_mission` is policy-free, ready for a `MissionExecutor` adapter for `evaluation/runner.py` |

Demo settings are not experiment results. `alpha = 0.3` was chosen so a 30-mission stream visibly
converges; it is not the frozen `config/experiment.yaml` value. Reward gaps between topologies are small
(about 0.01–0.03), so Section 2 is an illustration, not a held-out claim. The trust assumption is that the
simulated witness is honest (brief §8.5).

## Dashboard (Streamlit)

A thin local UI over the same functions the CLI uses (brief §15). It holds no business logic: every number
comes from `run_single_mission`, `execute_mission`, `feasible_topologies` or `run_experiment_a`, reshaped for
display by `src/samg/dashboard/data.py`.

```powershell
.venv\Scripts\python -m pip install streamlit plotly   # already listed in pyproject dependencies
.venv\Scripts\streamlit run src/samg/dashboard/app.py
```

Headless check: `streamlit run src/samg/dashboard/app.py --server.headless true --server.port 8765`, then
`http://localhost:8765/_stcore/health` returns `ok`. Uses `width="stretch"` for charts and tables, so it needs a
recent Streamlit (tested with 1.67).

Every run shows the mission ID, the config ID (`config_hash` of topology costs, allocation, reward and security
configs) and the seed. Each panel is labelled LIVE (computed now), REPLAYED (saved deterministic run),
AGGREGATE (saved evaluation) or SHADOW (evaluation only, never learned). Both labs with editable inputs have a
**Reset to saved demo configuration** button (judge mission, seed 7, adaptive LinUCB, alpha 0.3, CP-SAT).

| Tab | What it shows | Live or loaded |
| --- | --- | --- |
| Mission Control | Seed, judge or generated scenario (factor selectors), adaptive (LinUCB/UCB1) or fixed topology. Context vector, D030 eligibility with reasons, mean/bonus/score per arm and the choice, Plotly coordination graph (fixed agent positions, coordinators in red), assignment table and planned-vs-simulated Gantt, handoffs with `h0 + h1*hops` and the parameter values, simulator transitions, per-event validation trace, episode decision, ACP reward breakdown (term, weight, contribution), guarded update (applied or refused, `b` before/after). Expander: every eligible topology on the same mission and seed side by side (shadow, not fed to the learner). | Live. Fixed mode uses a fixed-topology policy, so LinUCB is never updated |
| Adaptive Evaluation Lab | Loads `artifacts/experiments/experiment_a*.json` (`ExperimentResult.model_dump_json()`): policy table with mean, std, 95% bootstrap CI, regret; paired comparisons; training learning curve (running mean of measured rewards); selection by family; seen vs held-out combos; the experiment config. With no file it says so and shows no numbers. | Aggregate (saved). A **development mode** button runs a tiny live `run_experiment_a` (6 train / 4 test, greedy), clearly marked as not the held-out evaluation |
| Security & Attack Lab | Trust-boundary box. Attack setup (compromised agent, preferred topology, inflation/deflation, schedule). Anatomy of the attacked judge mission: per-event auth stage (signature, role, freshness) and evidence stage with reason codes; episode decision; what S2 and S1 learned. Attack window S1 vs S2 from the same pre-attack state, summary counts, parameter divergence (A, b, theta per arm) and next-choice difference. | Saved `artifacts/experiments/experiment_c*.json` shown as raw JSON if present (REPLAYED); otherwise a live small run (same protocol as `samg demo` section 3) |

Development-mode executor: `samg.evaluation.executor.OrchestrationExecutor` is used if it exists; otherwise the
dashboard falls back to `data._DashboardExecutor`, a 10-line adapter that maps `execute_mission` onto
`MissionResult` (no persistence). The page names which one ran.

Tests: `pytest tests/unit/dashboard` (AppTest render, mission run, reset; helper consistency against the
records). They skip if Streamlit is not installed.
