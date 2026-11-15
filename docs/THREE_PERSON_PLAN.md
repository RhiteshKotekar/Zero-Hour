# SAMG — Three-Person Implementation Plan

Applies to: `github.com/RhiteshKotekar/Zero-Hour` (as of `591d490`, Phases 0–2 are implemented and the vertical-slice demo is on `main`; see [WORK_QUEUE.md](WORK_QUEUE.md))
Spec of record: `SAMG_Shunya_Final_Hackathon_Build_Brief.md` (shared outside this repo; referred to as "the brief", section numbers as `§`)
Build window: 24 hours, hour markers below are relative to kickoff (H0).
Allocator: CP-SAT with the deterministic greedy fallback, for the MVP and for Experiments A–C (D003, D029). A neural allocator baseline (Luttmann & Xie, ICAPS 2024; [PAPER_ALIGNMENT.md](PAPER_ALIGNMENT.md), D022–D029) is **post-hackathon, optional and local-only**. It is not in any phase, gate or fallback rule below; see [Later: neural allocator baseline (local only)](#later-neural-allocator-baseline-local-only).

## 0. Team and ownership

| Person | Mode | Owns (writes code in) | One-line responsibility |
| --- | --- | --- | --- |
| **Dev A** | Heavy, with Claude | `domain/mission.py`, `domain/graph.py`, `topology/`, `context/`, `allocation/`, `simulation/` (except witness), `evaluation/runner.py`, dashboard views 1–2 | **What happened**: missions, graphs, allocation, ground-truth execution, reward, performance experiments |
| **Dev B** | Heavy, with Claude | `domain/events.py`, `domain/canonical.py`, `assurance/`, `witness/`, `learning/`, `persistence/`, `orchestration.py`, `cli.py`, `evaluation/attacks.py`, dashboard view 3 | **What we believe and learn**: signing, ACP, witness, evidence admission, LinUCB/UCB, storage, attack experiments, vertical-slice integration |
| **Validator (V)** | Light, mostly manual | `tests/contract/fixtures/judge_mission.*` (data only), `docs/VALIDATION_LOG.md`, results tables, demo script | **Is it true**: installs, hand-checks numbers, runs tests/CLI, checks invariants and claims, runs the demo rehearsal |

Why this split: the learner's guarded update (INV-05) sits next to the ACP, so the whole security-critical path (report → ACP → admission → policy update) has one owner. Dev A never needs to touch it; Dev A only supplies plans, traces and the reward function. The two devs share only `samg.domain` and three config files, and each domain file has exactly one writer.

## 1. Working rules

### 1.1 Repository and branches

- `main` is always green. Work on `a/<topic>` and `b/<topic>` branches; V works on `v/<topic>`.
- Small PRs (one module or one feature). The *other* dev reviews interface changes only; V runs the PR checklist (§9.1).
- After the H2 contract freeze, any change to `samg.domain`, `config/*.yaml` keys, enum values, signed fields, feature order or reward terms requires: a `docs/DECISIONS.md` entry, updated fixtures, and a ping to the other dev.

### 1.2 Using Claude (Dev A and Dev B)

- Step 0 of Phase 0 adds a repo-root `CLAUDE.md` with: the module ownership table above, the dependency direction (`domain` ← everything; no peer-private imports), "every RNG takes an explicit seed", "only ADMITTED episodes update protected policy", and "do not edit files outside your ownership".
- Start each Claude session by pointing it at `CLAUDE.md`, the relevant brief sections (e.g. "implement §5.3–5.4 in `topology/`"), and the contract fixtures.
- Ask for tests first, then the implementation. Require `pytest` green before opening a PR.
- Don't let Claude "fix" a failing contract test by editing the contract — that is a DECISIONS-level change.
- Keep both Claude sessions off `samg.domain` at the same time; after H2 it is effectively read-only.

### 1.3 Definition of done (any task)

1. Unit tests exist and pass; randomness is seeded and the seed is a parameter.
2. Failures return structured reason codes (no `print`, no swallowed exceptions).
3. Public function has a docstring naming its domain input/output types.
4. V has ticked the PR checklist.

## 2. Reconcile repo docs with the brief (decision table)

The repo docs and the Final brief disagree in several places. This plan follows **the brief** (it is the frozen MVP). Dev B records these as `D009`–`D018` in `docs/DECISIONS.md` during Phase 0; V checks they are all present.

| # | Topic | Repo docs say | Brief says | Plan uses |
| --- | --- | --- | --- | --- |
| D009 | Team | 4 developers | 5 workstreams | 3 people, this document |
| D010 | Context features | 10 features | `x = [1, d, h, r, a]` (§6.1) | Brief: 4 features + intercept, version `ctx-v1` |
| D011 | Baselines | 3 fixed policies | P0-H/F/D, P1 best-fixed, P2 context-free UCB1, P3 LinUCB (§12.1) | Brief |
| D012 | Graph cost | per-edge latency/reliability/cost | `c(a,b) = h0 + h1·hops`, infeasible if no path (§5.4) | Brief; latency/reliability edge attributes are optional extras, not in the objective |
| D013 | Reward | 5 terms (0.45/0.20/0.15/0.10/0.10) | `0.65C + 0.15(1−T) + 0.10(1−R) + 0.10(1−H)` (§7.2) | Brief, weights in `config/reward.yaml` |
| D014 | Evidence | generic `EvidenceArtifact` | signed witness events from simulator task transitions + task-state machine (§8.5, §8.8) | Brief |
| D015 | Decisions | per report: VALID / REJECTED / INDETERMINATE | event: AUTHENTICATED / REJECTED / STALE / DUPLICATE / PROVISIONAL / DISPUTED / CORROBORATED; episode: ADMITTED / PROVISIONAL / REJECTED (§8.7, §8.4) | Brief. Only `ADMITTED` episodes update protected policy |
| D016 | Freshness | timestamp age + nonce | mission epoch + per-agent sequence; dedupe key `(mission_id, epoch, agent_id, seq)` (§8.6) | Brief; timestamp kept as a secondary check |
| D017 | Experiments | Exp 1 (adaptive), Exp 2 (security) | A (topology), B (context value), C (poisoning), D (optional replay/graph patch) (§12) | Brief |
| D018 | UI | Streamlit experiment viewer | 3 views: Mission Control, Adaptive Evaluation Lab, Security & Attack Lab (§15) | Brief; CLI is the fallback |

D022–D029 (2026-11-14) record the paper-alignment design for a deferred neural allocator baseline. None of them changes the hackathon scope: the deliverable stays inside brief §2.2, and the allocator for A–C is CP-SAT (D029). V does not need to check them before G0.

Target layout (keeps the repo's existing packages, adds the few the brief needs):

```text
config/            reward.yaml, topology_costs.yaml, security_policy.yaml, experiment.yaml
src/samg/
  domain/          enums.py, mission.py (A), graph.py (A), events.py (B), canonical.py (B)
  topology/        builder.py, templates.py, costs.py            (A)
  context/         features.py                                   (A)
  allocation/      greedy.py, cpsat.py                           (A)
  simulation/      scenarios.py, engine.py, reward.py            (A)
  witness/         service.py                                    (B)
  assurance/       identity.py, signatures.py, freshness.py, state_machine.py, admission.py, graph_policy.py (B)
  learning/        linucb.py, ucb1.py, fixed.py, vulnerable.py   (B)
  persistence/     db.py, repositories.py                        (B)
  evaluation/      runner.py, metrics.py (A); attacks.py (B)
  orchestration.py, cli.py                                       (B)
  dashboard/       app.py, view_mission.py, view_eval.py (A); view_security.py (B)
tests/unit/ tests/contract/fixtures/ tests/integration/
```

Public cross-owner interfaces (the only things the other side may import). These are the **implemented** signatures at `591d490`. They replace the original `(mission, agents, …)` draft (D020: builders take a `Scenario`; D030: eligibility includes allocation feasibility; D031: span-of-control durations come from the plan).

| Provider | Function | Used by |
| --- | --- | --- |
| A | `topology.build_graph(scenario, topology, costs=None) -> (TopologyEligibility, CoordinationGraph \| None)` | B (orchestration) |
| A | `topology.eligible_topologies(scenario, costs=None) -> (list[TopologyName], dict[TopologyName, TopologyEligibility])`, the structural check only | B (audit) |
| A | `allocation.feasible_topologies(scenario, costs=None, config=None) -> (eligible, verdicts, {topology: (graph, plan)})`. This is the eligibility that policies are offered (D030) | B (orchestration), A (runner) |
| A | `context.extract_features(scenario) -> MissionContext` (`features = (1, d, h, r, a)`, `ctx-v1`) | B (policies) |
| A | `allocation.allocate(scenario, graph, costs=None, config=None) -> AllocationPlan` | B (orchestration) |
| A | `simulation.run(scenario, graph, plan, seed, costs=None, *, duration_jitter=0.10, task_failure_probability=0.0, forced_failures=()) -> ExecutionTrace` (nominal durations taken from the plan, D031) | B (witness, reports) |
| A | `simulation.compute_metrics(scenario, graph, plan, outcomes, costs) -> GroundTruthMetrics`; `simulation.compute_reward(metrics \| None, config, *, weights="base") -> RewardBreakdown` | B (ACP recomputes reward, D033) |
| B | `orchestration.execute_mission(scenario, topology, settings, *, seed, decision_id, graph=None, plan=None, repo=None, mission_index=0, attack=None, forced_failures=()) -> MissionExecution`. It is policy-free, which makes it the basis for the runner's `MissionExecutor` | A (runner) |
| B | `orchestration.run_single_mission(scenario, world, settings, *, seed, mission_index=0, attack=None, forced_failures=()) -> MissionRunRecord` | A (UI), CLI |
| B | `learning.make_policy(kind, cfg, seed)` for `P0-H/F/D`, `P1`, `P2`, `P3`, `S1` | A (runner) |

## 3. Phase 0 — Contract freeze (H0–H2)

Goal: everyone can import the models, load fixtures, and agree on bytes that get signed.

### Dev A

1. Create `a/contracts`. Add `pyyaml` to dependencies and `hypothesis` to `dev` extras in `pyproject.toml` and `requirements.txt`; delete the stale "legacy `requirement.txt`" sentence in `Readme.md`.
2. Write `domain/enums.py`: `TopologyName {HIERARCHICAL, FUNCTIONAL_CELL, DISTRIBUTED}`, `TaskState {OPEN, ASSIGNED, EXECUTING, REPORTED_COMPLETE, VERIFIED_COMPLETE, BLOCKED, FAILED}`, `PolicyMode {PROTECTED, VULNERABLE}`. (B adds the event/episode enums in the same file in step B2; A merges first.)
3. Write `domain/mission.py`: `AgentProfile` (id, capabilities, capacity, resource budget, role/capability family, `can_coordinate`, `available`, `public_key_id`), `TaskSpec` (id, required capabilities, duration, resource demand, priority weight, `reward_critical`, dependencies), `MissionSpec` (id, epoch, tasks, deadline, generator version + params, family label). Validators: unique IDs, deps exist, no self-dependency, DAG check.
4. Write `domain/graph.py`: `CoordinationGraph` (JSON-safe nodes/edges + `graph_version`), `AllocationPlan` (assignments, schedule, objective terms incl. handoff cost per dependency edge with the path used, `feasible`, `solver`), `ExecutionTrace` (ordered task transitions with sim-time), `GroundTruthMetrics` (C, T, R, H raw and normalised), `RewardBreakdown`.
5. Write `config/topology_costs.yaml` (`h0`, `h1`, `max_path_hops`, `max_degree_distributed`, low/base/high sets) and `config/reward.yaml` (weights, normalisation ranges, clipping rule, failure outcome).

### Dev B

1. Write repo-root `CLAUDE.md` (§1.2) and `docs/DECISIONS.md` entries D009–D018.
2. Add to `domain/enums.py`: `EventType {TASK_STARTED, TASK_COMPLETE_CLAIM, REWARD_CLAIM, WITNESS_TRANSITION, GRAPH_PATCH}`, `EventStatus` and `EpisodeStatus` per D015.
3. Write `domain/canonical.py`: `canonical_bytes(model) -> bytes` (UTF-8, sorted keys, `separators=(",", ":")`, enums as values, datetimes as UTC ISO-8601, floats rounded to a fixed precision or encoded as strings — pick one and document it).
4. Write `domain/events.py`: `AgentEvent` (schema version, event id, mission id, epoch, agent id, sequence, event type, task id, payload, key id, signature) with `signed_payload_bytes()`; `WitnessEvent` (same shape, witness identity); `EventDecision`; `EpisodeRecord` (event decisions, admitted outcomes, recomputed reward, status, reason codes); `LearningEvent` (episode id, decision id, topology, context, reward, status). Protected policy accepts only `EpisodeStatus.ADMITTED`.
5. Write `config/security_policy.yaml`: role → allowed event types, witness identity, tolerances, max clock skew.
6. Create contract fixtures under `tests/contract/fixtures/`: (1) 2-agent 2-task reachable mission, (2) same with no permitted path, (3) honest signed claim + matching witness event, (4) signed false claim + contradicting witness event, (5) replayed event (same seq). Store a **golden** base64 of `signed_payload_bytes()` for fixture 3 so any change to canonicalisation breaks a test.

### Validator

1. Fresh clone, create a venv, `pip install -e ".[dev]"`, run `pytest`. Log Python version, OS and every error in `docs/VALIDATION_LOG.md`. (Windows: `.venv\Scripts\activate`.)
2. Transcribe the judge scenario from brief §3.2–3.3 (agents A0–A5, tasks T1–T8 with dependencies) into `tests/contract/fixtures/judge_mission.yaml` using Dev A's schema once it lands (~H1.5). Ask A to make it load under `MissionSpec`.
3. Tick off D009–D018 in `DECISIONS.md` against §2 of this plan.
4. Turn the phase checklists in this file into GitHub issues (one per numbered step, labelled A/B/V).

**Gate G0 (H2), all three:** `from samg.domain import *` works; all 6 fixtures load; golden-signature test passes; `pytest` collects and passes contract tests. After G0, `samg.domain` is frozen.

## 4. Phase 1 — Independent slices (H2–H8)

### Dev A — graph, features, scenarios, allocation

1. `topology/builder.py`: base typed graph (node types: mission, task, agent, capability; edges: `depends_on`, `requires`, `can_perform`, `coordinates_with`) per §5.1.
2. `topology/templates.py`: the three deterministic templates per §5.3 — hierarchical (coordinator → every active agent, pairs route through it), functional-cell (cells by capability family, member ↔ cell coordinator, cell coordinator ↔ mission lead A0), distributed (direct edges between eligible agents of each dependency edge, capped degree, deduped). Deterministic tie-break by agent ID. Return `Ineligible(reason)` when no coordinator exists or a mandatory dependency has no path.
3. `topology/costs.py`: all-pairs hop distances on the coordination subgraph; `handoff_cost(a, b)` = 0 if same agent, `h0 + h1·hops` if a path exists, `None` (infeasible) otherwise.
4. `context/features.py`: `ctx-v1` = `[1, d, h, r, a]` — dependency density, mean pairwise Jaccard distance of available agents' capabilities, resource scarcity, availability ratio; documented missing-value rule.
5. `simulation/scenarios.py`: seeded generator over the 5 factors in §3.4 (dependency structure, capability distribution, resource pressure, availability, task profile); stores generator version + params; family label kept for reporting only; produces dev/train/test seed lists plus held-out factor combinations. Assert each mission is feasible for at least one topology.
6. `allocation/greedy.py` first (deterministic ordering per repo `ARCHITECTURE.md`, same marginal handoff cost). Then `allocation/cpsat.py`: `x[t,a]`, pairwise `y[i,j,a,b]` for each dependency edge, start-time variables with precedence + handoff delay, capacity/resource limits; objective = weighted duration + handoff cost + resource use + load imbalance; solver time limit and seed from config; fall back to greedy if no feasible incumbent; record `solver` used.
7. Tests: each template on the judge mission yields the expected edges; **changing topology changes the objective value or the assignment on the judge mission** (the §12.10 "graph is decorative" check); unreachable fixture is infeasible; greedy is identical across 3 repeated calls; CP-SAT objective ≤ greedy objective on fixtures.

### Dev B — identity, signatures, freshness, state machine, storage, learners

1. `assurance/identity.py`: registry `agent_id/key_id → public key, role, permissions, active`. Generate Ed25519 keys deterministically from the scenario seed (`Ed25519PrivateKey.from_private_bytes(32 seeded bytes)`), keep private keys in memory only.
2. `assurance/signatures.py`: sign/verify over `signed_payload_bytes()`, URL-safe base64; malformed signature → `REJECTED`.
3. `assurance/freshness.py`: active epoch check + dedupe on `(mission_id, epoch, agent_id, seq)` and on event ID; returns `STALE` / `DUPLICATE`.
4. `assurance/state_machine.py`: transitions from §8.8; an agent claim can reach `REPORTED_COMPLETE` only; only the witness can set `VERIFIED_COMPLETE`; no `ASSIGNED → VERIFIED_COMPLETE` jump; agents report only on their own tasks.
5. `persistence/db.py` + `repositories.py`: `sqlite3`, `PRAGMA foreign_keys=ON`, append-only tables: `experiments`, `missions`, `graph_snapshots`, `topology_decisions`, `allocation_plans`, `outcomes`, `events_received` (UNIQUE dedupe key), `event_decisions`, `episodes_trusted`, `episodes_quarantined`, `learning_events`, `policy_state`, `evaluation_runs`. No private-key columns.
6. `learning/linucb.py`: `A_k = λI`, `b_k = 0`, `np.linalg.solve` (no explicit inverse), score logging for all arms, deterministic tie-break by `TopologyName`, seeded balanced warm-up; `observe(event)` raises `IneligibleLearningEvent` unless `ADMITTED`; idempotent on episode ID (INV-08); state snapshot/restore for cloning. `learning/ucb1.py` (P2, §6.5), `learning/fixed.py` (P0-H/F/D and P1 helper "best on training"), `learning/vulnerable.py` (`VulnerableLinUCB`, accepts authenticated agent-claimed reward; never the default wiring).
7. Tests: signature tamper/unknown key/wrong role; replay; Hypothesis property test on random transition sequences for the state machine; LinUCB on a known 2-step matrix; protected policy raises on PROVISIONAL/REJECTED and on a duplicate episode; DB restart keeps dedupe.

### Validator

1. **Handoff-cost oracle:** with `h0`, `h1` from `config/topology_costs.yaml`, hand-compute (spreadsheet) the handoff cost of one fixed assignment of the judge mission under each topology (e.g. hierarchical: two non-coordinator agents = 2 hops → `h0 + 2·h1`). Give the three numbers to Dev A as test oracle values.
2. **LinUCB check:** with `d = 5`, `λ = 1`, verify by NumPy one-liner that after one update with reward `r`, `θ = (I + xxᵀ)⁻¹ r x` matches the value Dev B's test asserts.
3. **Reward check:** compute `0.65C + 0.15(1−T) + 0.10(1−R) + 0.10(1−H)` for 3 metric sets (all-best, all-worst, one mixed); confirm `[0, 1]` and give values to Dev A.
4. **Feature check:** compute `d` and `h` by hand for the judge mission (8 tasks, 7 dependency edges in the T1→…→T8 chain; max DAG edges for 8 tasks = 28 → `d = 0.25`).
5. Run `pytest` on `main` after every merge; log pass/fail counts with the commit hash.
6. PR checklist on every PR (§9.1).

**Gate G1 (H8):** A's allocator returns a feasible plan on the judge mission under all three topologies with different handoff costs (matching V's oracle); B's ACP primitives and learners pass their unit tests; V's log shows `main` green.

## 5. Phase 2 — Execution, evidence, vertical slice (H8–H14)

### Dev A

1. `simulation/engine.py`: execute a plan under a seed — duration jitter, per-hop handoff delay, seeded task failure probability, capacity consumption — and emit an `ExecutionTrace` (OPEN → ASSIGNED → EXECUTING → … with sim-times) plus a private ground-truth record for the evaluation oracle.
2. `simulation/reward.py`: `compute_reward(metrics, weights) -> RewardBreakdown` (raw metric, normalised value, weighted contribution per term); invalid plan → predefined failure outcome, never a normal reward.
3. Topology-cost ablation switch (`h0 = h1 = 0`) for §12.9.
4. Hand A's public function list (§2) to B as a short `docs/INTERFACES.md` with example calls.

### Dev B

1. `witness/service.py`: converts trace transitions into `WitnessEvent`s signed with the witness's own key (separate identity, §8.5).
2. Agent report generator: honest agents sign claims derived from the trace; per-agent monotonically increasing `seq`.
3. `assurance/admission.py`:
    - `validate_event()` → AUTHENTICATED / REJECTED / STALE / DUPLICATE (§8.2).
    - corroboration of claims against witness events → CORROBORATED / DISPUTED / PROVISIONAL.
    - `admit_episode()` → ADMITTED / PROVISIONAL / REJECTED (§8.4). A single disputed claim is quarantined but the episode can still be ADMITTED if witness evidence covers every reward-critical task. Reward is **recomputed** via `compute_reward` from admitted outcomes, never copied from a claim.
4. `orchestration.py`: `run_single_mission(config, policy_mode, seed)` = scenario → features → eligible topologies → policy select → graph → allocate → simulate → witness + reports → ACP → persist → `observe()` only if ADMITTED.
5. `cli.py`: `python -m samg run --seed 7 --policy linucb --mode protected` prints mission ID, topology scores, assignment, handoff costs, reward breakdown, event/episode decisions.
6. `tests/integration/test_vertical_slice.py`: one deterministic mission end to end; a validly signed false claim with contradicting witness evidence **changes `VulnerableLinUCB` and leaves protected `A_k`, `b_k` byte-identical**.

### Validator

1. Run the CLI on the judge mission for seeds 1, 2, 3. Re-run each seed and `diff` the outputs: they must be identical (determinism).
2. Open the SQLite file (`sqlite3 samg.db`) and check: no column holds private keys; `learning_events` rows with `applied_at` set = number of ADMITTED episodes; inserting a duplicate dedupe key fails.
3. Build the **invariant trace table** in `docs/VALIDATION_LOG.md`: INV-01…INV-09 (§8.9) → the test that proves each. Any invariant without a test goes back to Dev B as an issue.

**Gate G2 (H14) — the critical milestone:** CLI runs the full loop for the judge mission in protected mode; the integration test passes. If this is late, apply the fallback rules (§8) before starting Phase 3.

## 6. Phase 3 — Attacks and experiments (H14–H19)

### Dev B — Experiment C (+ optional D)

1. `evaluation/attacks.py`: deterministic schedule in which one compromised, authorised agent signs a fresh but false completion + inflated reward claim, biased toward an attacker-chosen topology.
2. Snapshot the pre-attack LinUCB state; clone into S1 (`VulnerableLinUCB`) and S2 (protected). Feed both identical contexts, seeds, attack schedule and subsequent clean missions.
3. Measure: unsupported reports submitted/admitted, legitimate reports submitted/blocked (FRR), policy updates from unsupported reports, matrix divergence (`‖A_S1 − A_S2‖`, `‖θ_S1 − θ_S2‖`), topology-selection shift, subsequent held-out reward. Report counts with denominators.
4. Tune attack magnitude on **dev** seeds only until S1 measurably shifts; freeze the attack config before the recorded run (§12.5).
5. Optional, only after 1–4 work: replay test (old event / obsolete epoch → rejected, zero duplicate updates); a missing-witness configuration showing PROVISIONAL and no learning; corruption levels 0 / 20 / 40 % if time allows.

### Dev A — Experiments A and B

1. `evaluation/runner.py`: dev / train / held-out-test splits by seed and held-out factor combos; persist seed lists and config hash.
2. Run P0-H, P0-F, P0-D on training; choose P1 from training results only.
3. Train P2 (UCB1) and P3 (LinUCB) on the same training stream; tune `alpha` on dev only.
4. **Freeze** `alpha`, `h0/h1`, reward weights into `config/experiment.yaml` with a hash at ~H16. No changes after this.
5. Evaluate all six policies on ≥ 20 paired held-out seeds; mean, std, 95 % bootstrap CI; stratify by family; report infeasibility rate separately.
6. Counterfactual shadow evaluation (§12.3): all three topologies on the same held-out mission/seed for simulator-oracle regret. Shadow rewards never reach the learner.
7. Ablations (§12.9): P2 vs P3; topology cost set to zero; `h0/h1` low/base/high; two alternative reward-weight sets.
8. `evaluation/metrics.py` writes CSV + JSON manifest per run (§13.5).

### Validator

1. Run a small script that checks dev ∩ train ∩ test seed sets are pairwise empty and that the frozen config hash in results matches `config/experiment.yaml`.
2. Fill the two results tables (§12.11) **only by copying from runner CSV output**; note the run ID next to each table.
3. Go through the §12.10 falsification list and write, for each claim, "supported / not supported / parameter-sensitive" with the number behind it. This decides what the pitch is allowed to say.
4. Confirm S1's state actually changed (divergence > 0) and S2 admitted zero unsupported reports; if either fails, flag it immediately.

**Gate G3 (H19):** both experiment manifests reproduce from a clean checkout; results tables are filled from measured output.

## 7. Phase 4 — UI, stabilisation, demo (H19–H24)

### Dev A

1. `dashboard/app.py` (Streamlit, imports existing functions only, no business logic) with View 1 **Mission Control** (§15.3): config panel, decision panel with all arm scores, graph panel with path lengths and handoff costs, assignment/timeline, reward breakdown.
2. View 2 **Adaptive Evaluation Lab** (§15.4): fixed-topology benchmark, learner comparison, learning curve, held-out results, counterfactual comparison, robustness checks — all loaded from persisted runs.

### Dev B

1. View 3 **Security & Attack Lab** (§15.5): attack setup, validation trace per event, S1 vs S2 side by side, FRR panel, trust-boundary disclosure text.
2. One-click "reset to saved demo"; save one clean and one attack demo bundle (DB + manifest) under `artifacts/`.
3. CLI fallback commands documented in README.

### Validator

1. Run the UI acceptance tests in §15.3, §15.4 and §15.5 click by click; every view must show mission ID, config ID, seed, and live/replayed/aggregate status.
2. Follow the README quick start on a clean machine/venv; fix the README text (V may edit README prose).
3. Time the 4-minute (§15.7) and 3-minute (§15.8) demos; record a backup screen video (§15.9).
4. Prepare a one-page judge Q&A sheet from §16 and a limitations slide from §17, using only claims marked "supported" in Phase 3. If judges ask about learned allocators, answer that a neural baseline following Luttmann & Xie (ICAPS 2024) is planned as post-hackathon comparison work, and claim no result for it.

**H23 code freeze.** Only demo-blocking bug fixes after this, each with V re-running the demo.

## 8. Fallback rules (from brief §14.1, in the order to apply)

1. CP-SAT blocks G2 → ship greedy allocator; disclose it.
2. UI not stable by H21 → CLI output + saved graph images.
3. Replay, graph-patch and agent-failure reallocation are dropped before any main experiment.
4. Never drop: one typed graph with three templates and graph-derived handoff cost; LinUCB + UCB1 + one held-out evaluation; the witness and evidence admission; the signed false-report attack.

## 9. Validator reference

### 9.1 PR checklist (copy into each PR review)

- [ ] Tests added for the new behaviour; `pytest` green locally (paste the count).
- [ ] Every random source takes a seed argument (`grep -rn "random\.\|default_rng()" src/` shows no unseeded calls).
- [ ] No import of another owner's private module (`grep -rn "from samg\.\(topology\|allocation\|simulation\|assurance\|learning\)\." src/` only hits public functions in §2).
- [ ] No change to `samg/domain`, enum values or config keys without a DECISIONS entry.
- [ ] Failures return reason codes; no `print` used for errors.
- [ ] Nothing named `Vulnerable*` is used in default wiring.

### 9.2 Standing checks after every merge

- `pytest` pass/fail counts + commit hash → `docs/VALIDATION_LOG.md`.
- CLI seed-7 output unchanged unless the PR says it should change.

## 10. Sync points and risks

| Hour | Sync (15 min, all three) | Decision taken |
| --- | --- | --- |
| H2 | G0 contract freeze | Domain frozen |
| H5 | Progress | Is CP-SAT on track or go greedy-first? |
| H8 | G1 | Start integration |
| H11 | Progress | Is G2 reachable by H14? Apply fallbacks if not |
| H14 | G2 vertical slice | Start experiments |
| H16 | Parameter freeze | Hash `config/experiment.yaml` |
| H19 | G3 results | What the pitch may claim |
| H21 | UI go / no-go | UI or CLI demo |
| H23 | Code freeze | Rehearse |

| Risk | Early sign | Response |
| --- | --- | --- |
| CP-SAT model too slow with `y[i,j,a,b]` | > 5 s on the judge mission at H5 | Time limit + greedy fallback; restrict `y` to capability-eligible pairs |
| Topology makes no difference | G1 test "topology changes objective" fails | Fix templates/costs before anything else; this is the core claim |
| Attack does not move S1 | divergence ≈ 0 on dev seeds | Increase claim magnitude / frequency on dev only, then freeze |
| LinUCB doesn't beat P1 or P2 | held-out CI overlaps | Report it honestly (§12.10); do not retune on test |
| Two Claude sessions drift from contracts | contract tests fail after a merge | Revert, then change via DECISIONS entry |
| Merge conflicts in `domain/` | any PR touching both `mission.py` and `events.py` | One writer per file; domain frozen after H2 |

## Later: neural allocator baseline (local only)

**Outside the 24-hour timeline (D028).** This work starts only after the hackathon submission, or after the §18 MVP checklist is complete. Nothing in §3–§8 depends on it. It is an optional **comparison baseline** for CP-SAT, following Luttmann & Xie (ICAPS 2024). It runs only on the developer laptop that has an Intel Arc XPU. The design is in [PAPER_ALIGNMENT.md](PAPER_ALIGNMENT.md) and the decisions in D022–D029.

### Ownership (same A/B line as the MVP)

| Person | Writes | Responsibility |
| --- | --- | --- |
| Dev A | `allocation/validate.py` (`validate_plan`), `allocation/neural_adapter.py`, `nco/env.py`, `nco/features.py`, Experiment E in `evaluation/runner.py` | Allocation semantics: the MDP's masks, transition and reward, all built on the existing `allocation.common.evaluate`; the plan validator; fallback wiring (INV-12); Experiment E |
| Dev B | `nco/model.py`, `nco/train.py`, `nco/decode.py`, `nco/checkpoint.py`, `model_checkpoints` / `nco_training_runs` / `allocator_evaluations` tables | Learning machinery and its trust boundary: HAM encoder + hierarchical decoder, Pa-POMO training, decoding, checkpoint integrity (INV-10, INV-11) |
| Validator | `tests/contract/fixtures/nco_masks_judge.json` (data only), `docs/VALIDATION_LOG.md` | Hand-written mask oracle, device benchmark log, checkpoint-hash re-check, seed-range overlap check, determinism diff |

Because `samg.domain` is frozen after G0, these additions need their own DECISIONS entry and updated fixtures when the work starts: `SolverName.NEURAL_HAM` (UPPERCASE value per D020), the extra `AllocationPlan` fields and `config/nco.yaml`.

### Steps

1. **A:** `allocation.validate_plan`, the CP-SAT constraint set plus graph reachability, returning reason codes. CP-SAT and greedy plans must pass it.
2. **A:** `nco/env.py` and `nco/features.py` per PAPER_ALIGNMENT §3.1.
   - Tests: masks equal V's `nco_masks_judge.json`; a Hypothesis property test that every random masked rollout ends in a `validate_plan`-accepted plan or an explicit dead end; changing topology changes the agent mask or hop features on the judge mission.
3. **B:** `nco/model.py`, in plain PyTorch with **no PyG**.
   - **Device benchmark:** time one forward and backward pass at batch 256 on CPU and on XPU (separate venv, torch 2.15.0+xpu) for both sizes in `config/nco.yaml`, and print `param_count`. Pick the device per D027; on an XPU error, use CPU.
   - **Checkpoint registry:** `nco/checkpoint.py` refuses a hash mismatch or a non-`FROZEN` row before deserialising, and uses `weights_only=True`.
4. **B:** `nco/train.py` (Pa-POMO), capped at about 3 h on the XPU, plus `nco/decode.py` (greedy, seeded sampling, beam with a fixed tie-break).
5. **A:** `allocation/neural_adapter.py`: `load_frozen` → `decode` → best by `evaluate` → `validate_plan`. On failure it falls back to CP-SAT, then greedy, with `fallback_reason`.
6. **B:** select a checkpoint on `nco-dev` only. Gate: 100 % validator pass and mean gap ≤ 5 % to CP-SAT. If it passes, freeze one SHA-256; if not, reject all candidates and report that.
7. **A:** Experiment E (EXPERIMENTS.md, D029) on `nco-test`, locally. Experiments A–C are not re-run, except as an optional allocator-sensitivity check.
8. **V:** hash re-check (`Get-FileHash … -Algorithm SHA256`) against the manifest; seed-range overlap check; two identical CLI runs with `--allocator neural`; Experiment E table copied from CSV only.

### Rules for Claude sessions on this work

- No PyTorch Geometric.
- Training happens only in the separate XPU venv; the project `.venv` keeps CPU torch or no torch.
- Recorded inference runs on CPU with deterministic algorithms.
- Nothing under `nco/` imports `persistence`, `assurance` or report/witness code.
- Every `torch.load` uses `weights_only=True`, through `checkpoint.load_frozen` only.
- No MARL, LLMs or other learners.
- Give Claude PAPER_ALIGNMENT §1 and §3.1, and do not let it invent paper details. If the authors' MIT-licensed `rl4msprp` code is adapted, keep its licence notice.

### Risks

| Risk | Early sign | Response |
| --- | --- | --- |
| Training too slow on the laptop (the paper took 4–27 h on an A100) | Dev gap not improving after about 1 h | Switch to the small config (`d_h = 64`, `L = 2`) and a smaller `W`, or stop |
| XPU failure (`UR_RESULT_ERROR_OUT_OF_RESOURCES` or similar) | Benchmark or training errors | Use CPU with the small config. Never use PyG on XPU. |
| Mask/validator mismatch | `validate_plan` rejects neural plans | Treat it as an env bug. Fallback keeps runs valid; report the fallback rate. |
| Neural only matches CP-SAT at SAMG size | Gap ≈ 0 | This is the expected result ([P] Table 5, PRP20). Report parity plus runtime; claim nothing more. |
| RAM pressure (15.4 GB) | Swapping | Lower the batch size |
