# SAMG: context file for AI assistants

> **Who this file is for.** It is written for an AI assistant (ChatGPT, Claude, Copilot or another), not for people. A team member pastes it into a chat, or points the assistant at it, so the assistant can explain the project and help with the work. People should start with [`Readme.md`](../Readme.md) and [`DEMO.md`](DEMO.md).
>
> Snapshot: `main` at commit `591d490` (integration/demo merged), 2026-11-15. When this file disagrees with the code, the code is right. Tell the user about the mismatch.

---

## 0. Instructions to the assistant

You are helping a member of the **SAMG** hackathon team (repository `github.com/RhiteshKotekar/Zero-Hour`). There are three teammates:

- **Dev A** owns missions, graphs, allocation, simulation and the performance experiments.
- **Dev B** owns events, assurance, witness, learning, persistence, orchestration and the attack experiment.
- **Validator (V)** installs, hand-checks numbers, runs tests and the CLI, and decides which claims the results support.

Experience levels vary across the team.

1. **Ask, or infer, the level** the person wants: a one-paragraph overview, a walk-through, or code-level detail. Answer at that level. Define every acronym the first time you use it (see §3).
2. **Cite file paths** (and function names) for every technical statement, e.g. "`src/samg/allocation/feasibility.py::feasible_topologies`". Paths are relative to the repo root.
3. **Never invent results.** Experiment numbers come only from `docs/WORK_QUEUE.md` (results log R1–R9), `docs/RESULTS*.md` (if it exists; see §11), `docs/VALIDATION_LOG.md`, or from running the commands in §9. If a number is not in those places, say that it has not been measured yet. Do not estimate it.
4. **Never invent APIs.** Signatures in this file were checked against the code at `591d490`. If the person's checkout differs, read the source before advising.
5. **Respect ownership and the hard rules** in §12 when proposing edits. If an edit falls outside the person's ownership column, say so and suggest they ask the owner.
6. Distinguish **demo settings** from **experiment settings** (§7.4) and **integration-minimal** modules from complete ones (§10).
7. If asked something this file does not cover, say so and point to the most relevant doc in §5.

---

## 1. What SAMG is (one paragraph)

**SAMG, Secure Adaptive Mission Graphs**, is a *controlled Python simulation*. It controls no robots, drones or live systems; every agent, report, piece of evidence and adversary is simulated. A small team of heterogeneous simulated agents (A0–A5 in the judge mission) must carry out a mission of dependent tasks (T1–T8). For each mission:

1. A **contextual bandit** (LinUCB) picks one of three **coordination topologies** (hierarchical, functional-cell or distributed).
2. That topology becomes an *executable* coordination graph.
3. OR-Tools **CP-SAT** allocates tasks to agents under that graph.
4. A seeded simulator executes the plan.
5. Agents send **signed** claims about what happened. An independent **witness** signs what it actually observed.
6. The **Assurance Control Plane (ACP)** decides whether the mission is trustworthy enough to learn from, and recomputes the reward itself from witness evidence.

It is a modular Python monolith with local SQLite. There are no services, Docker, React or Node (D001).

## 2. The two claims SAMG must demonstrate

| # | Claim | Experiment | How it is measured |
| --- | --- | --- | --- |
| 1 | **Adaptive coordination:** choosing the topology per mission context (LinUCB, P3) beats the best fixed topology (P1, Experiment A). Context adds value over a context-free bandit (UCB1, P2, Experiment B). | A, B (brief §12) | Held-out test missions, paired seeds, mean ± 95 % bootstrap CI, simulator-oracle regret. Runner: `src/samg/evaluation/runner.py::run_experiment_a`. |
| 2 | **Secure learning:** a correctly signed but **false** report does not change the protected learner (S2 = `LinUCBPolicy`). It does change a deliberately vulnerable learner (S1 = `VulnerableLinUCB`), which trusts authenticated claims. | C (brief §9.2, §12.5) | False claims submitted/corroborated, honest claims blocked (false-rejection rate, FRR, with denominators), ‖A_S1−A_S2‖, ‖θ_S1−θ_S2‖, shift in topology choices. Currently shown by the demo, Section 3. The full harness is in progress. |

The core security idea: **a signature proves who wrote a report (authorship), not that the report is true.** Truth comes from independent witness evidence. Experiment D (replay, graph patches) is optional. Experiment E (a neural allocator against CP-SAT) is deferred and local-only (D029).

---

## 3. Glossary

| Term | Meaning in SAMG |
| --- | --- |
| **Topology / arm** | `TopologyName` (`src/samg/domain/enums.py`): `HIERARCHICAL`, `FUNCTIONAL_CELL`, `DISTRIBUTED`. Each one is a bandit arm. |
| HIERARCHICAL | One hub coordinator (the mission lead if available, else the first `can_coordinate` agent by ID) is linked to every other available agent. Every other pair routes through the hub. |
| FUNCTIONAL_CELL | Available non-hub agents are grouped into cells by `role`. Members of a cell are linked directly, and each cell coordinator links to the hub. Cross-cell handoffs go coordinator → hub → coordinator. |
| DISTRIBUTED | For each dependency edge, the capable agents of the prerequisite are linked directly to the capable agents of the dependent, in sorted order. A link is skipped when either endpoint already has `distributed_max_degree` (3) links. |
| **Coordination graph** | `CoordinationGraph` (`src/samg/domain/graph.py`): a typed graph with mission/task/capability/agent nodes and edges `HAS_TASK, REQUIRES, DEPENDS_ON, CAN_PERFORM, COORDINATES_WITH`. `graph_version` is a content hash. It is *executable*: hop counts drive handoff cost, delay, feasibility and span-of-control slowdown. |
| **Hops / handoff** | A dependency T_i → T_j whose two tasks have different assignees is a handoff. Its cost is `h0 + h1·hops` along the shortest permitted path. It costs 0 when both tasks have the same agent and is infeasible with no path or more than `max_path_hops` hops (D012). |
| **Eligibility** | A topology is *eligible* only if it can be built **and** CP-SAT finds a feasible plan for it (D030, `feasible_topologies`). `eligible_topologies` is the structural check only. |
| **ACP** | Assurance Control Plane (`src/samg/assurance/`). It verifies signatures, roles, freshness, payloads and task-state transitions; corroborates claims against witness evidence; admits or rejects the episode; and recomputes the reward. |
| **Witness** | A separate simulated identity, `WITNESS-0` (`config/security_policy.yaml`). It signs `WitnessEvent`s from the simulator's task transitions (`src/samg/witness/service.py`). It is assumed honest (brief §8.5); this is the trust assumption. |
| **Event / claim** | `AgentEvent` (signed by an agent: `TASK_STARTED`, `TASK_COMPLETE_CLAIM`, `REWARD_CLAIM`, `GRAPH_PATCH`) or `WitnessEvent` (`WITNESS_TRANSITION`). Both are in `src/samg/domain/events.py`. |
| **Event statuses** | `EventStatus`. From `validate_event`: `AUTHENTICATED` (signature, role, freshness, payload and state checks all pass), `REJECTED`, `STALE`, `DUPLICATE`. After corroboration: `CORROBORATED` (the witness agrees), `DISPUTED` (the witness contradicts), `PROVISIONAL` (no witness evidence) (D015). |
| **Episode statuses** | `EpisodeStatus`. `ADMITTED` means the witness covers every reward-critical task and the reward is ACP-recomputed. `PROVISIONAL` means a reward-critical task is unverified. `REJECTED` means an infeasible plan, wrong mission or an illegal witness transition. **Only `ADMITTED` may update a protected policy.** |
| **Reward source** | `RewardSource.ACP_RECOMPUTED` (protected learners accept only this) or `AGENT_CLAIM` (used only by `VulnerableLinUCB`). |
| **Quarantine** | A `DISPUTED` claim is quarantined (`DISPUTED_CLAIM_QUARANTINED`). The episode can still be `ADMITTED` from witness evidence alone. |
| **LinUCB** | A disjoint linear upper-confidence-bound contextual bandit, one ridge model per arm: `score = θᵀx + α·sqrt(xᵀA⁻¹x)`. Code: `src/samg/learning/linucb.py::LinUCBPolicy`. This is P3, and S2 in Experiment C. |
| **UCB1** | A context-free bandit: `mean + c·sqrt(2 ln N / n)`. Code: `src/samg/learning/ucb1.py::UCB1Policy`. This is P2. |
| **P0–P3** | The baseline set (D011). P0-H/P0-F/P0-D always pick one fixed topology. P1 is the best fixed topology chosen **on training data only**. P2 is UCB1. P3 is LinUCB. Build them with `samg.learning.make_policy(kind, cfg, seed)`, where `kind` is one of `P0-H, P0-F, P0-D, P1, P2, P3, S1`. |
| **S1 / S2** | The two learners in Experiment C. S1 = `VulnerableLinUCB` (learns from the last *authenticated* `REWARD_CLAIM`; Experiment C only, never default wiring). S2 = protected `LinUCBPolicy`. Both start from the same cloned pre-attack state. |
| **Context `ctx-v1`** | `x = [1, d, h, r, a]` (D010, `src/samg/context/features.py`). The terms are: intercept; dependency density `d = edges / (n(n−1)/2)`; capability heterogeneity `h` = mean pairwise Jaccard distance; resource scarcity `r` = demand / budget, clipped; availability `a` = available / registered. |
| **C, T, R, H** | Reward terms (§7.2): weighted completion, makespan/deadline, resource use, coordination overhead. Each is normalised to [0, 1]. |
| **Span of control** | D031. An agent with `degree` coordination links works `1 + span_overhead·max(0, degree − 1)` times slower. |
| **Judge mission** | `M-judge-001` from `src/samg/simulation/scenarios.py::judge_scenario`. It has agents A0–A5 and an 8-task chain T1→…→T8 (brief §3.2–3.3). |
| **Dev/train/test seeds** | Disjoint seed lists from `seed_splits(master_seed, n_dev, n_train, n_test)`. Tune on dev only. The test split is held out and run once after freezing `config/experiment.yaml`. |
| **Design seeds** | Seeds ≥ 50 000 (`samg.evaluation.landscape.DESIGN_SEED_OFFSET`) are used for design/landscape analysis. They never overlap experiment seeds. |
| **D-numbers** | Decisions D001–D033 in `docs/DECISIONS.md` (summarised in §8). |
| **INV-numbers** | Invariants. INV-01…INV-09 come from brief §8.9 (the brief is shared outside the repo). INV-10…INV-13 apply only to the deferred neural baseline. See §8.2. |
| **R-numbers** | The results log in `docs/WORK_QUEUE.md` (R1–R9). |
| **G0–G3** | Gates in `docs/THREE_PERSON_PLAN.md`: G0 contract freeze, G1 slices, G2 vertical slice, G3 results. |
| **"The brief"** | `SAMG_Shunya_Final_Hackathon_Build_Brief.md`. It is shared outside this repo and cited as `§N`. If you do not have it, do not guess its contents. |

---

## 4. End-to-end pipeline (exact functions)

The loop is `src/samg/orchestration.py::run_single_mission`. Every step below was checked against the code.

```text
Scenario ─► extract_features ─► feasible_topologies ─► policy.select ─► execute_mission ─► _learn/offer_learning_event
                                                                  │
         build_graph? ─► allocate? ─► simulation.run ─► WitnessService.observe ─► draft_reports (+apply_attack) ─► sign_reports
                                                                  │
                                       validate_event (per event, receipt order) ─► admit_episode ─► EpisodeRecord
```

| # | Step | Function (module) | Input → output |
| --- | --- | --- | --- |
| 0 | Configs | `RunSettings.load(config_dir=None, *, use_cpsat=None)` (`orchestration.py`) | YAML in `config/` → `RunSettings(costs: TopologyCostConfig, allocation: AllocationConfig, reward: RewardConfig, security: SecurityPolicy)` |
| 0 | World | `World.create(policy, *, mode=PolicyMode.PROTECTED, policy_instance=None, db_path=":memory:")` | → `World(repo: Repository, policy, policy_instance, mode)`. It raises if `VulnerableLinUCB` is used in PROTECTED mode or the other way round. |
| 1 | Scenario | `judge_scenario(seed=0)` or `generate_scenario(seed, factors=None)` (`simulation/scenarios.py`) | → `Scenario(scenario_id, seed, mission: MissionSpec, agents: tuple[AgentProfile], permitted_links)` |
| 2 | Context | `extract_features(scenario)` (`context/features.py`) | → `MissionContext(features=(1,d,h,r,a), feature_schema_version="ctx-v1", mission_id, feature_names)` |
| 3 | Eligibility (D030) | `feasible_topologies(scenario, costs=None, config=None)` (`allocation/feasibility.py`) | → `(eligible: list[TopologyName], verdicts: dict[TopologyName, TopologyEligibility], plans: dict[TopologyName, (CoordinationGraph, AllocationPlan)])`. Internally it calls `build_graph` and then `allocate` for every arm. |
| 4 | Select | `policy.select(context.features, eligible, context.feature_schema_version)` (`learning/*.py`) | → `PolicyDecision(topology \| None, eligible, scores, means, bonuses, warmup, reason_codes, …)`. If no arm is eligible: `topology=None` with `NO_ELIGIBLE_TOPOLOGY`. |
| 5 | Persist intent | `repo.add_mission(...)`, `repo.add_topology_decision(...)` (`persistence/repositories.py`) | Append-only SQLite rows |
| 6 | Execute (policy-free) | `execute_mission(scenario, topology, settings, *, seed, decision_id, graph=None, plan=None, repo=None, mission_index=0, attack=None, forced_failures=())` | → `MissionExecution(graph, plan, trace, ground_truth_reward, witness_events, agent_events, auth_decisions, final_decisions, false_claim_event_ids, attacked, episode, acp_metrics, acp_reward, claimed_reward)` |
| 6a | Graph (only if not passed in) | `build_graph(scenario, topology, costs=None)` (`topology/templates.py`) | → `(TopologyEligibility, CoordinationGraph \| None)` |
| 6b | Allocate (only if not passed in) | `allocate(scenario, graph, costs=None, config=None)` (`allocation/__init__.py`) | → `AllocationPlan`. CP-SAT is the default. Greedy runs when `use_cpsat: false`, or with `fallback_used=True` if CP-SAT finds no incumbent without proving infeasibility. |
| 6c | Keys | `mission_keys(scenario, security)` → `build_identities(seed, roles)` (`assurance/identity.py`) | → `(IdentityRegistry, KeyRing)`. Ed25519 keys are derived from the seed (D019). Private keys stay in `KeyRing` only. |
| 6d | ACP session | `open_session(scenario, plan, registry, policy, seen, repo=None)` (`assurance/admission.py`) | → `ACPSession`. `seen` is `DbSeenStore(repo)` or `InMemorySeenStore()`. |
| 6e | Simulate | `simulation.run(scenario, graph, plan, seed, costs=None, *, duration_jitter=0.10, task_failure_probability=0.0, forced_failures=())` (`simulation/engine.py`) | → `ExecutionTrace(transitions, outcomes, metrics: GroundTruthMetrics, …)`. Raises `ValueError` on an infeasible plan. |
| 6f | Ground-truth reward | `compute_reward(trace.metrics, settings.reward)` (`simulation/reward.py`) | → `RewardBreakdown` (**evaluation only**, never learned from) |
| 6g | Witness | `WitnessService(witness_id, registry, ring).observe(trace, base_time)` (`witness/service.py`) | → `list[WitnessEvent]`, signed by `WITNESS-0` |
| 6h | Agent reports | `draft_reports(trace, plan, observed_reward)` → optional `apply_attack(drafts, trace, plan, true_reward, attack, *, agents)` → `sign_reports(drafts, *, mission_id, epoch, base_time, registry, ring)` (`witness/reports.py`, `evaluation/attacks.py`) | → `(list[AgentEvent], oracle: dict[event_id, is_false_claim])`. The oracle is for evaluation only. |
| 6i | Validate | `validate_event(session, event, now=event.issued_at)` for each event in `receipt_order(witness, agent)` | → `EventDecision(status ∈ {AUTHENTICATED, REJECTED, STALE, DUPLICATE}, reason_codes)` |
| 6j | Admit | `admit_episode(session, received, *, graph, episode_id, topology_decision_id, reward_config, costs)` | → `Admission(episode: EpisodeRecord, final_decisions, metrics, breakdown)`. Corroboration (`corroborate`) turns AUTHENTICATED claims into CORROBORATED, DISPUTED or PROVISIONAL. The reward is recomputed by `compute_metrics` + `compute_reward` from **witness outcomes** (`witness_outcomes(session)`). |
| 7 | Learn | `_learn(...)` → `offer_learning_event(world, event)` → `policy.observe(event)` | Protected: only `ADMITTED` + `ACP_RECOMPUTED`, through `ProtectedGate.admit` (`learning/base.py`), which calls `LearningEvent.require_protected_eligible()`. A non-admitted episode is recorded with `INELIGIBLE_STATUS` and never offered. Vulnerable: `reward = claimed_reward`, source `AGENT_CLAIM`. |
| 8 | Snapshot | `repo.add_policy_snapshot(...)` | Policy state after the mission |

Other entry points:

- `run_stream(scenarios: Sequence[(Scenario, seed)], world, settings, *, start_index=0, attack=None) -> list[MissionRunRecord]`.
- `replay_events(scenario, record, world, settings, events)`. This is the replay attack: the events come back `DUPLICATE`, and the re-offered episode is refused with `DUPLICATE_EPISODE`.
- `MissionRunRecord.deterministic_dump()` drops the solver `runtime_ms`.

Experiment runner: `run_experiment_a(cfg: ExperimentConfig, executor: MissionExecutor, *, costs=None, extra_hash_configs=(), progress=None) -> ExperimentResult` (`evaluation/runner.py`). The executor is injected through the `MissionExecutor` protocol: `execute(scenario, topology, *, seed, decision_id) -> MissionResult(feasible, ground_truth_reward, episode, metrics, detail)`. **No real executor adapter has been merged on `main` yet** (queue item 11). It should wrap `execute_mission`, which `MissionExecution` is shaped for (`feasible`, `ground_truth_reward.reward`, `episode`, `metrics_dict()`).

---

## 5. Repository map

Owners come from `CLAUDE.md`. "Integration" means the module is a minimal integration version written for the vertical slice (see §10).

```text
config/
  topology_costs.yaml   A   h0, h1, link_cost, max_path_hops, handoff delay, hop failure p, degree cap, span_overhead, sensitivity sets
  allocation.yaml       (not listed in CLAUDE.md; Dev A in practice) CP-SAT objective weights and solver settings
  reward.yaml           A   reward weights, alternative weight sets, failure outcome
  experiment.yaml       A   Experiment A/B protocol (seeds, split sizes, alpha, lam, warm-up, ucb_c, frozen flag)
  security_policy.yaml  B   witness id, role→event types, freshness, corroboration tolerances, admission rules
src/samg/
  __main__.py           B*  `python -m samg` → cli.main
  cli.py                B   argparse: `demo`, `run` (integration)
  demo.py               B*  the three-section terminal demo: run_demo, run_one, DemoConfig (integration)
  orchestration.py      B   RunSettings, World, execute_mission, run_single_mission, run_stream, replay_events (integration)
  domain/               shared contracts, frozen after G0
    enums.py            shared  A block (TopologyName, TaskState, PolicyMode, CapabilityMatch, NodeKind, EdgeKind, SolverName, IneligibilityReason, AllocationFailure) / B block (EventType, EventStatus, EpisodeStatus, IdentityRole, RewardSource, ReasonCode)
    mission.py          A   AgentProfile, TaskSpec, MissionSpec, Scenario
    graph.py            A   CoordinationGraph, GraphNode/Edge, TopologyEligibility, Assignment, Handoff, ObjectiveTerms, AllocationPlan
    execution.py        A   TaskTransition, TaskOutcome, GroundTruthMetrics, ExecutionTrace, RewardBreakdown
    config.py           A   TopologyCostConfig, AllocationConfig, RewardConfig, load_* helpers, config_hash
    events.py           B   AgentEvent, WitnessEvent, EventDecision, EpisodeRecord, LearningEvent, IneligibleLearningEvent
    canonical.py        B   canon-v1 canonical JSON/bytes/hash (what gets signed)
  topology/             A   templates.py (build_graph, eligible_topologies), builder.py (base graph, eligible_agents), costs.py (HopTable, max_coordination_cost)
  context/features.py   A   extract_features → MissionContext (ctx-v1)
  allocation/           A   common.py (AllocationProblem, evaluate), cpsat.py, greedy.py, feasibility.py (feasible_topologies), __init__ (allocate)
  simulation/           A   scenarios.py (judge_scenario, generate_scenario, factor_grid, seed_splits, split_factor_combos); engine.py run (integration); reward.py compute_metrics/compute_reward (integration)
  witness/              B   service.py WitnessService (integration); reports.py draft_reports, sign_reports, reporting_agent (integration)
  assurance/            B   identity.py, signatures.py, freshness.py, state_machine.py, policy.py (complete); admission.py validate_event/corroborate/admit_episode (integration)
  learning/             B   base.py (PolicyDecision, ProtectedGate, ARM_ORDER), linucb.py, ucb1.py, fixed.py, vulnerable.py, __init__ (make_policy)
  persistence/          B   db.py (SQLite schema, append-only triggers), repositories.py (Repository, DbSeenStore)
  evaluation/           runner.py + metrics.py (A): Experiment A/B; landscape.py (A*, design analysis R7/R8); attacks.py (B): AttackConfig, apply_attack (integration)
  dashboard/            only __init__.py so far. Planned: app.py, view_mission.py, view_eval.py (A), view_security.py (B), D018
tests/
  unit/                 per-module tests (allocation, topology, features, scenarios, simulation, evaluation, landscape, assurance/, learning/, persistence/)
  contract/             test_domain_contracts.py, test_event_contracts.py, make_fixtures.py (B), fixtures/01–05 *.json
  integration/          test_vertical_slice.py (end to end, attack, replay, determinism, demo)
docs/                   shared; see below
```

`*` = not named in the `CLAUDE.md` ownership table. The owner shown is inferred from `DEMO.md` or the work queue.

Docs:

| File | Use it for | Status |
| --- | --- | --- |
| `THREE_PERSON_PLAN.md` | Current team plan, phases, gates, validator checklist | Current; overrides `IMPLEMENTATION_PLAN.md` |
| `DECISIONS.md` | D001–D033 | Current. **Later decisions override earlier docs.** |
| `WORK_QUEUE.md` | Task queue and results log R1–R9 | Current |
| `DEMO.md` | How to run the CLI demo, and what each section shows | Current |
| `VALIDATION_LOG.md` | Validator's reproduction checklist and results rows | Started; V fills it |
| `PAPER_ALIGNMENT.md` | Deferred neural allocator baseline (Luttmann & Xie, ICAPS 2024) | Current, deferred scope |
| `ARCHITECTURE.md`, `DATA_MODEL.md`, `SECURITY_MODEL.md`, `EXPERIMENTS.md` | Original design | **Partly stale.** Read them with D010–D021 and D030–D033 applied. Examples: the 5-term reward, `ValidationStatus.VALID/INDETERMINATE`, nonce-based replay, the `AgentReport`/`EvidenceArtifact` models and "Experiment 1/2" naming are all superseded. |
| `IMPLEMENTATION_PLAN.md` | Old four-developer plan | Superseded (D009) |

---

## 6. Domain contracts (field names, units, enum values)

**Units.** All simulated time is in **milliseconds** (`duration_ms`, `deadline_ms`, `handoff_delay_ms_per_hop`, `Assignment.start/end`, `WitnessEvent.sim_time_ms`). The judge mission's minute values are multiplied by 60 000 (D020). CP-SAT internally works in whole seconds (`time_unit_ms: 1000`) and reports milliseconds. The allocation objective expresses `makespan` and `max_agent_load` in **minutes** (ms / 60 000).

**Enum values are UPPERCASE strings and equal to their names** (e.g. `TopologyName.FUNCTIONAL_CELL == "FUNCTIONAL_CELL"`). They are persisted and signed, so never change them without a DECISIONS entry (D020).

Key models (Pydantic, `src/samg/domain/`):

- `AgentProfile`: `agent_id`, `role` (drives functional cells), `capabilities`, `capacity` (max tasks per mission), `resource_budget`, `can_coordinate`, `is_mission_lead`, `available`, `public_key_id`.
- `TaskSpec`: `task_id`, `name`, `required_capabilities`, `capability_match` (`ALL`/`ANY`), `duration_ms`, `resource_demand`, `priority_weight` (default 1.0), `mandatory`, `reward_critical`, `dependencies`.
- `MissionSpec`: `schema_version="mission-v1"`, `mission_id`, `epoch`, `scenario_id`, `tasks`, `deadline_ms`, `generator_version`, `generator_params`, `family` (a reporting label only, **never a policy feature**). The validator rejects dependency cycles.
- `Scenario`: `scenario_id`, `seed`, `mission`, `agents`, `permitted_links` (`None` means every pair is permitted; a link must be permitted in both directions).
- `AllocationPlan`: `plan_id` (a deterministic hash), `mission_id`, `topology`, `graph_version`, `feasible`, `solver` (`CP_SAT`/`GREEDY`), `solver_status`, `fallback_used`, `runtime_ms` (wall clock, excluded from deterministic dumps), `assignments[Assignment(task_id, agent_id, start, end)]`, `unassigned_tasks`, `handoffs[Handoff(prerequisite_task, dependent_task, from_agent, to_agent, hops, path, cost, delay)]`, `objective: ObjectiveTerms`, `reason_codes: AllocationFailure`, `detail`, `config_version`.
- `GroundTruthMetrics`: `weighted_completion` (C), `makespan`, `duration_norm` (T), `resource_used`, `resource_norm` (R), `coordination_cost`, `coordination_norm` (H), `mandatory_completed`, `communication_failures`.
- `RewardBreakdown`: `reward_schema_version="reward-v1"`, `weights`, `components` (C, 1−T, 1−R, 1−H), `contributions` (weight × component), `reward ∈ [0,1]`, `failure_outcome`, `failure_label`.
- `AgentEvent` / `WitnessEvent`: `schema_version="evt-v1"`, `event_id`, `mission_id`, `epoch`, `seq`, `event_type`, `task_id`, `issued_at` (an aware datetime), `payload`, `key_id`, `signature` (URL-safe base64 Ed25519). They also carry `kind` (`AGENT_EVENT`/`WITNESS_EVENT`) plus `agent_id`, or `witness_id, from_state, to_state, sim_time_ms`. The signature covers `signed_payload_bytes()` = canon-v1 of every field except `signature` (D019).
- `EventDecision`: `decision_id`, `event_id`, `mission_id`, `epoch`, `signer_id`, `event_type`, `task_id`, `status`, `reason_codes`, `corroborating_event_ids`.
- `EpisodeRecord`: `episode_id`, `mission_id`, `epoch`, `topology_decision_id`, `topology`, `plan_id`, `event_decisions`, `admitted_task_states`, `reward` (**present if and only if ADMITTED**), `reward_terms`, `reward_schema_version`, `status`, `reason_codes`.
- `LearningEvent`: `event_id`, `episode_id`, `decision_id`, `topology`, `feature_schema_version`, `context`, `reward`, `reward_source`, `status`. `require_protected_eligible()` raises `IneligibleLearningEvent(reason)` unless the event is `ADMITTED` with `ACP_RECOMPUTED`.

Task states (`TaskState`): `OPEN, ASSIGNED, EXECUTING, REPORTED_COMPLETE, VERIFIED_COMPLETE, BLOCKED, FAILED`. Allowed transitions and actors are in `src/samg/assurance/state_machine.py::TRANSITIONS`. An agent may only move `ASSIGNED→EXECUTING` and `EXECUTING→REPORTED_COMPLETE`. Only the witness may set `VERIFIED_COMPLETE`, `FAILED` or `BLOCKED`. The terminal states for admission are `VERIFIED_COMPLETE` and `FAILED`.

Freshness (D016): the dedupe key is `(mission_id, epoch, signer_id, seq)`, plus event-ID uniqueness. The timestamp is a secondary check (`max_clock_skew_seconds: 5`, `max_event_age_seconds: 300`). Event ids look like `{mission_id}/e{epoch}/{signer_id}/{seq}` (D032).

Schema/version strings: `mission-v1`, `graph-v1`, `plan-v1`, `trace-v1`, `reward-v1`, `evt-v1`, `canon-v1`, `ctx-v1`, `gen-v1`, `linucb-v1`, `ucb1-v1`, `fixed-v1`, `db-v1`. The integration modules use `sim-v0-integration`, `witness-v0-integration`, `acp-v0-integration`, `attack-v0-integration` and `orch-v0-integration`.

SQLite tables (`src/samg/persistence/db.py::TABLES`, all append-only with triggers): `experiments, missions, graph_snapshots, topology_decisions, allocation_plans, outcomes, events_received, event_decisions, episodes_trusted, episodes_quarantined, learning_events, policy_state, evaluation_runs`. No table has a private-key column.

---

## 7. Cost, objective and reward model (current values)

### 7.1 Coordination cost (`config/topology_costs.yaml`, `topo-cost-v1`)

| Parameter | Value | Meaning |
| --- | --- | --- |
| `h0` | 1.0 | Fixed cost of any cross-agent handoff (D012) |
| `h1` | 0.5 | Cost per hop |
| `link_cost` | 0.25 | Per undirected coordination link the topology maintains (D021, proposed). The YAML comment says "D019", which is a typo. |
| `max_path_hops` | 4 | A longer path counts as no permitted path |
| `handoff_delay_ms_per_hop` | 120 000 | 2 simulated minutes per hop, added before the dependent task may start |
| `hop_failure_probability` | 0.02 | Per hop. Up to 3 attempts (`MAX_HOP_ATTEMPTS`); if all fail, the message is lost and the dependent task is BLOCKED |
| `distributed_max_degree` | 3 | Degree cap for DISTRIBUTED |
| `span_overhead` | 0.10 | D031, predeclared. 0 disables it |
| sensitivity | low `h0=0.5,h1=0.25`; base `1.0, 0.5`; high `2.0, 1.0` | For §12.9 ablations (`TopologyCostConfig.with_setting(name)`) |

Formulas:

- Handoff cost: `c(a,b) = 0` if `a == b`; `h0 + h1·hops` if a permitted path exists with `hops ≤ max_path_hops`; infeasible otherwise. Code: `TopologyCostConfig.handoff_cost(hops)`, `HopTable.route(a, b)`.
- Handoff delay: `hops × handoff_delay_ms_per_hop`, plus one extra hop delay per retransmission in the simulator.
- Coordination overhead: `H_raw = Σ cost of planned handoffs whose prerequisite completed + link_cost × |coordination links|`.
- Normaliser: `max_coordination_cost(n_deps, n_agents, costs) = n_deps·(h0 + h1·max_path_hops) + link_cost·n_agents(n_agents−1)/2`, or 1.0 if that is 0. `n_agents` counts *available* agents. Then `H = clip(H_raw / bound)`.
- Span of control (D031): `effective_duration(task, agent) = duration_ms × (1 + span_overhead × max(0, degree(agent) − 1))`. It is used by CP-SAT, greedy and `evaluate`. The simulator takes the nominal duration from the plan (`assignment.end − assignment.start`) and applies jitter `U(0.9, 1.1)` (`duration_jitter=0.10`).

### 7.2 Allocation objective (`config/allocation.yaml`, `alloc-v1`, minimised)

`weighted_total = 1.0·makespan_min + 10.0·handoff_cost + 0.0·resource_use + 0.25·max_agent_load_min + 1000·unserved_priority`

CP-SAT settings: `time_limit_s: 5.0`, `num_workers: 1` (for determinism), `random_seed: 0`, `time_unit_ms: 1000`. `use_cpsat: true`. The objective terms come from `allocation/common.py::evaluate`, which CP-SAT and greedy share.

### 7.3 Reward (`config/reward.yaml`, `reward-v1`; D013, normalisation D033)

```text
r = clip01( 0.65·C + 0.15·(1 − T) + 0.10·(1 − R) + 0.10·(1 − H) )
C = completed priority weight / total priority weight
T = clip01(makespan / deadline_ms)      (makespan = latest end of a completed task; T = 1 if nothing completed)
R = clip01(resource demand of every task that started / total budget of the agents the plan assigned)
H = clip01((handoff cost of handoffs whose prerequisite completed + link_cost·links) / max_coordination_cost)
```

- Alternative weight sets for sensitivity: `completion_heavy {0.75, 0.10, 0.075, 0.075}` and `efficiency_heavy {0.55, 0.20, 0.10, 0.15}`. Select one with `compute_reward(metrics, cfg, weights="completion_heavy")`.
- Infeasible plan: `compute_reward(None, cfg)` returns `failure_reward = 0.0` with `failure_label = "INVALID_PLAN"`. The episode is REJECTED with `INFEASIBLE_PLAN` and is never learned from.
- The same `compute_metrics` serves the simulator (ground truth) and the ACP (witness outcomes). Times are integer milliseconds, so with a faithful witness the ACP reward equals the ground-truth reward exactly.

**Worked example.** This is demo Section 1: the judge mission, seed 7, HIERARCHICAL with hub A0, CP-SAT. It comes from `python -m samg demo` at `591d490` and is reproducible.

- The deadline is 1.5 × the serial sum of 225 min, i.e. 337.5 min.
- 4 cross-agent handoffs of 2 hops each: `4 × 2.0 = 8.00`. There are 5 links, so `H_raw = 8.00 + 0.25×5 = 9.25`. With `bound = 7×(1+0.5×4) + 0.25×15 = 24.75`, `H = 0.374`.
- `T = 242.3/337.5 = 0.718`.
- `R = 25.0/34.0 = 0.735`, where 34.0 is the summed budgets of A2, A3 and A4.
- `C = 1`.
- `r = 0.65 + 0.15×0.282 + 0.10×0.265 + 0.10×0.626 = 0.7814`.
- Allocation objective: `241.0 + 10×8.00 + 0.25×105.0 = 347.25`.

### 7.4 Learner parameters: three different sets, do not mix them up

| Where | alpha | lam | warm-up per arm | Other |
| --- | --- | --- | --- | --- |
| `LinUCBPolicy` constructor defaults | 1.0 | 1.0 | 1 | `dim=5`. The warm-up order is a seeded permutation of `ARM_ORDER`. |
| `config/experiment.yaml` (`exp-v1`, `frozen: false`) | 0.5 | 1.0 | 2 | `master_seed 2026`, `n_dev 10`, `n_train 60`, `n_test 20`, `holdout_fraction 0.2`, `ucb_c 1.0`, `bootstrap_seed 7` |
| Demo (`samg.demo.DemoConfig`) | 0.3 | (default) | (default) | `judge_seed 7`, `n_learn 30`, `n_attack 10`, `stream_seed_base 5000`, attacker `A4` preferring `FUNCTIONAL_CELL`, `inflation 0.20`, `deflation 0.30` |

`alpha` must be tuned on **dev** seeds only and then frozen (item 12). The demo value of 0.3 is **not** an experiment result. `ARM_ORDER` is alphabetical by value, `(DISTRIBUTED, FUNCTIONAL_CELL, HIERARCHICAL)`, and ties go to the earliest arm in that order.

---

## 8. Decisions and invariants

### 8.1 Decisions D001–D033 (one line each: decision → consequence)

| ID | Decision | Consequence |
| --- | --- | --- |
| D001 | Modular Python monolith with local SQLite | No services or infra; ownership is by module |
| D002 | The topology graph is operational (NetworkX) | Graph shape changes feasibility, cost and delay; it is not decorative |
| D003 | CP-SAT with a deterministic greedy fallback (reaffirmed by D022) | `plan.solver` and `fallback_used` are recorded and any fallback must be disclosed |
| D004 | Signed claims are separate from validated outcomes | A report is never a learner input; only the ACP produces learnable outcomes |
| D005 | Append-only SQLite audit log | Triggers block UPDATE/DELETE; corrections are new rows |
| D006 | Pydantic at every cross-package boundary | Field names, enums and units are validated |
| D007 | Record seeds, schemas and solver config | Every run must be replayable |
| D008 | `sqlite3` now, SQLAlchemy optional | No ORM in the code |
| D009 | Three-person team (Dev A / Dev B / Validator) | `THREE_PERSON_PLAN.md` replaces the four-developer plan |
| D010 | Context `ctx-v1 = [1, d, h, r, a]` | The 10-feature schema in `EXPERIMENTS.md` is obsolete |
| D011 | Baselines P0-H/F/D, P1, P2 (UCB1), P3 (LinUCB) | P1 isolates the value of adaptation; P2 isolates the value of context |
| D012 | Handoff cost `h0 + h1·hops`, 0 for the same agent, infeasible with no path | Per-edge latency/reliability are not objective terms |
| D013 | Reward `0.65C + 0.15(1−T) + 0.10(1−R) + 0.10(1−H)` | The 5-term reward in `ARCHITECTURE.md` is obsolete |
| D014 | Evidence = signed witness events + task-state machine | The generic `EvidenceArtifact` is obsolete |
| D015 | Event statuses (7) and episode statuses (3); only ADMITTED updates | `VALID/INDETERMINATE` in the older docs are obsolete |
| D016 | Freshness by epoch + per-signer seq; timestamp is secondary | Nonce-based replay in `SECURITY_MODEL.md` is obsolete |
| D017 | Experiments A (adaptation), B (context), C (poisoning), D (optional replay/patch) | "Experiment 1/2" in `EXPERIMENTS.md` map to A/B and C |
| D018 | Three Streamlit views (Mission Control, Adaptive Evaluation Lab, Security & Attack Lab); CLI fallback | Views are not built yet; the CLI demo is the fallback |
| D019 | canon-v1 encoding; seeded Ed25519 keys; `reward_source`; reward present iff ADMITTED; roles AGENT/COORDINATOR/WITNESS | A golden-signature test locks the bytes |
| D020 | Field names follow the fixtures (`capacity`, `duration_ms`, `deadline_ms`, `priority_weight`); ms units; UPPERCASE enums; `Scenario`; `build_graph(scenario, topology, costs)`; hub rule | It replaced the `(mission, agents, …)` signatures in plan §2 |
| D021 | *Proposed:* `H` includes `link_cost × links` | Without it, hop cost alone makes DISTRIBUTED dominate. Must be in the sensitivity check and ratified by the team |
| D022 | Neural allocator = deferred, optional, local-only comparison baseline | It is not in the hackathon MVP. CP-SAT stays the reference |
| D023 | Neural baseline: heterogeneous graph view derived from the typed graph (deferred) | NetworkX remains the source of truth |
| D024 | Neural baseline: HAM encoder + task→agent hierarchical decoder with hop/dependency biases (deferred) | The graph reaches the neural model |
| D025 | Neural baseline: Pa-POMO offline training, then freeze one checkpoint (deferred) | No online allocator learning |
| D026 | INV-05 restated; INV-10…13 for model artefacts (only if the baseline is enabled) | Training data never comes from reports or episodes; checkpoints are hash-pinned |
| D027 | Compute policy: the MVP needs no torch; the baseline trains on the Intel Arc XPU in a separate venv, without PyTorch Geometric | The project `.venv` stays torch-free or CPU-only |
| D028 | The neural baseline sits outside the 24-hour timeline | No gate depends on it |
| D029 | Experiments A–C use CP-SAT; Experiment E is optional and local | Neural results are never in the hackathon tables |
| D030 | Eligibility = buildable **and** allocatable (`feasible_topologies`, `ALLOCATION_INFEASIBLE`) | Infeasibility is reported per topology; the policy never pays for an arm it could have avoided |
| D031 | Span-of-control cost, `span_overhead = 0.10` | Durations depend on (task, agent, topology); creates a real trade-off (R8) |
| D032 | *Proposed by the integrator:* evidence-path conventions (witness signs `VERIFIED_COMPLETE`; simulated clock `SIM_BASE_TIME + index days + sim_time_ms`; event-id format; validation order; corroboration rules; one honest reward-claimer; separate SQLite worlds for S1/S2) | Dev B may revise them; each is isolated in `witness/`, `admission.py` or `orchestration.py` |
| D033 | *Proposed; Dev A to confirm:* reward normalisation edge cases (see §7.3) | The protected reward and the evaluation oracle use identical arithmetic |

### 8.2 Invariants

- **INV-01…INV-09** are defined in brief §8.9, which is not in this repo. Do not quote their exact wording unless the user supplies the brief. The repo enforces these ones, and cites the IDs in code:
  - **INV-05**: only `ADMITTED` episodes with `ACP_RECOMPUTED` reward update protected policy state. Enforced by `LearningEvent.require_protected_eligible`, `ProtectedGate.admit` and the orchestration guard in `_learn`.
  - **INV-08**: at most one update per episode, idempotent across restarts. Enforced by `ProtectedGate` (`DUPLICATE_EPISODE`) and `persistence/db.py`.
  - The Validator's task (`THREE_PERSON_PLAN.md` §5) is to map INV-01…09 to proving tests in `docs/VALIDATION_LOG.md`.
- Non-negotiables from `ARCHITECTURE.md` that still hold:
  - IDs are immutable and unique.
  - A signature is not truth.
  - `Vulnerable*` code is isolated to Experiment C.
  - Graph paths affect both allocation and simulation.
  - All randomness and solver settings are explicit and recorded.
- **INV-10…INV-13** apply only if the neural baseline is enabled (D026):
  - INV-10: training data comes only from the generator and `evaluate`.
  - INV-11: a checkpoint loads only if its SHA-256 is FROZEN, with `weights_only=True`.
  - INV-12: every neural plan passes `validate_plan`, or the allocator falls back.
  - INV-13: the nco seed ranges are disjoint from each other and from the experiment seeds.

---

## 9. Install, test, run

Python ≥ 3.11 is required; 3.12 is tested. The MVP needs no PyTorch, GPU or NPU.

**Windows (PowerShell), the minimal install used for the demo:**

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install pydantic networkx numpy ortools pyyaml pytest hypothesis cryptography
.venv\Scripts\python -m pip install -e . --no-deps
.venv\Scripts\python -m pytest -q -p no:cacheprovider
.venv\Scripts\python -m samg demo
```

**POSIX (bash):**

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install pydantic networkx numpy ortools pyyaml pytest hypothesis cryptography
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m samg demo
```

The full install is `pip install -e ".[dev]"`. It also pulls `streamlit`, `plotly`, `matplotlib` and `SQLAlchemy`, which are listed in `pyproject.toml` but not needed by the CLI or tests.

| Command | What it does |
| --- | --- |
| `python -m samg demo` | Three sections: the clean judge run, a 30-mission learning stream, and the signed false-report attack (S1 against S2) plus replay. About 10–20 s with CP-SAT, depending on the machine. |
| `python -m samg demo --greedy` | The same with the greedy allocator |
| `python -m samg demo --alpha 0.5 --n-learn 20 --n-attack 6` | Other demo settings (`--n-learn ≥ 4`, `--n-attack ≥ 1`) |
| `python -m samg run --seed 7 --policy linucb --mode protected` | One judge mission, printed step by step |
| `python -m samg run --seed 7 --policy linucb --mode vulnerable --attack` | A4 signs a false reward claim and `VulnerableLinUCB` learns it |
| `python -m samg run --seed 3 --policy ucb1` | Policies: `linucb`, `ucb1`, `fixed-h`, `fixed-f`, `fixed-d` |
| `python -m samg run --seed 11 --scenario generated` | A generated mission instead of the judge mission |

Other `run` options: `--compromised A4`, `--prefer FUNCTIONAL_CELL|HIERARCHICAL|DISTRIBUTED`, `--alpha`, `--greedy`. `--mode vulnerable` requires `--policy linucb`.

Determinism check:

- Windows: `.venv\Scripts\python -m samg demo > a.txt; .venv\Scripts\python -m samg demo > b.txt; fc a.txt b.txt`
- POSIX: `diff <(.venv/bin/python -m samg demo) <(.venv/bin/python -m samg demo)`

No wall-clock values are printed.

Contract fixtures are regenerated with `python tests/contract/make_fixtures.py` (Dev B only). `test_fixtures_are_current` guards against drift.

**Experiments A/B.** There is no CLI command yet. `run_experiment_a(load_experiment(), executor)` needs a `MissionExecutor` adapter over `execute_mission`, which is queue item 11 and in progress on a separate branch. Until it is merged, no Experiment A/B result exists on `main`.

---

## 10. Current status (from `docs/WORK_QUEUE.md` and `docs/DEMO.md`)

**Done on `main` (`591d490`)**

- Phase 0–1 (Dev A): domain contracts, topology templates and costs, `ctx-v1` features, seeded generator (feasible by construction, R5), CP-SAT + greedy, D030 eligibility, D031 span cost, landscape analysis.
- Dev B primitives: identity, signatures, freshness, state machine, LinUCB/UCB1/fixed/Vulnerable, SQLite persistence, contract fixtures 01–05.
- Experiment A/B runner and metrics (`evaluation/runner.py`, `evaluation/metrics.py`), tested with a synthetic oracle executor.
- The **vertical slice** (queue items 7 and 9): simulator, witness, ACP admission, orchestration, the CLI demo and `tests/integration/test_vertical_slice.py`. The full suite has 298 tests passing. The demo output is byte-identical across runs.

**Integration-minimal (working, but written by the integrator; the owner may replace it)**

| Module | Missing |
| --- | --- |
| `simulation/engine.py` | Capacity drain, agent failure/reallocation, ground-truth oracle record |
| `simulation/reward.py` | Dev A has not confirmed D033 yet |
| `witness/service.py`, `witness/reports.py` | Minimal, but they work |
| `assurance/admission.py` | No graph-patch validation (§8.3): `GRAPH_PATCH` claims stay PROVISIONAL |
| `evaluation/attacks.py` | Deterministic schedule and inflate/deflate claims only. No dev-seed tuning, no FRR over clean missions, no held-out metrics |
| `orchestration.py`, `cli.py`, `demo.py` | They work. `execute_mission` is ready for a `MissionExecutor` adapter |

**In progress (parallel agents, not on `main` yet)**

- Item 11: real `MissionExecutor` adapter; Experiments A/B on dev; tune `alpha` on dev.
- Item 12: freeze `config/experiment.yaml` (hash), held-out test run, results table, §12.10 falsification checklist.
- Item 13: ablations (`span_overhead`, `h0/h1`, `link_cost`, topology cost = 0, reward weight sets).
- Item 15: Experiment C harness (S1 against S2) with a frozen attack config and FRR with denominators.
- Item 16: Streamlit dashboard views 1–2 (D018). The CLI stays the fallback.
- Item 17: demo bundles, README quick-start check, Validator hand-off.

**Paused**

- Item 8: neural baseline (local, XPU). Data generation finished: 26,797 training instances, 26,444 of them CP-SAT-feasible. Training and evaluation are paused on a usage limit. `docs/NCO_RESULTS.md` does not exist yet. This work is outside the hackathon scope (D022, D028).

**Not started:** item 14 (simulator hardening), item 18 (PR to `main`, needs user approval), item 19 (neural Experiment E).

---

## 11. Known results so far (R1–R9) and what they mean

All of these come from `docs/WORK_QUEUE.md`. R7 and R8 are *planning-time landscape* analyses on design seeds. **They are not Experiment A results.**

| ID | Result | Meaning |
| --- | --- | --- |
| R1 | Dev A's models were aligned to Dev B's UPPERCASE enums and fixture field names; the skipped mission-fixture test now passes | One shared contract (D020) |
| R2 | With hop cost alone, DISTRIBUTED always wins when eligible, and FUNCTIONAL_CELL can never beat HIERARCHICAL on the judge mission | Led to the D021 link cost (proposed) |
| R3 | The ICAPS 2024 paper applies only to the allocation step | Neural baseline deferred (D022–D029) |
| R4 | The task→agent decoder barely shrinks decisions at SAMG size | The neural baseline is expected to match CP-SAT at best; any advantage needs 16/32-task missions |
| R5 | The old generator produced mostly infeasible missions (100/646 pairs feasible). After the fix, 633/643 are feasible, and all 10 failures are DISTRIBUTED | Contract: every generated mission is feasible under HIERARCHICAL. Led to D030 |
| R6 | `feasible_topologies` (D030). Generated scenario 16 is the regression case | Policies see only allocatable arms |
| R7 | Without span cost, DISTRIBUTED is the best planned topology on about 90 % of missions, with a mean margin of about 0.013 | Experiment A would have been trivial. Led to D031 |
| R8 | With `span_overhead = 0.10`, the best-topology shares are D 56 % / H 28 % / F 16 %; margins are about 0.008 reward | Something to learn now, but effect sizes will be **small**. Report them with CIs and the sensitivity sweep |
| R9 | Vertical slice merged (`591d490`): 298 tests pass and the demo output is byte-identical across runs. Demo Section 3 (demo settings): the ACP corroborates 0 of 10 false claims, honest claims blocked are 0/177, and S2 picks the attacker's preferred FUNCTIONAL_CELL 0/10 times. S1 learns from the claimed reward 10/10 times, picks FUNCTIONAL_CELL 7/10 times, and would next choose FUNCTIONAL_CELL for the judge mission (S2 would choose DISTRIBUTED). Replay is refused for both | End to end, the pipeline works, and the attack separates S1 from S2. This is a demo illustration, **not** the Experiment C result. See `WORK_QUEUE.md` R9 |

Files that **may not exist yet**:

- `docs/RESULTS.md` (or `RESULTS_*.md`): to be written by items 11–13 and 15 from runner CSV/JSON output.
- `docs/NCO_RESULTS.md`: item 8, paused.
- `artifacts/` demo bundles: item 17.
- `dashboard/app.py`: item 16.
- `tests/contract/fixtures/judge_mission.*`: owned by the Validator. Not created; the judge mission currently lives in code (`judge_scenario`).

If a teammate asks for Experiment A/B/C numbers and these files are absent, say that the numbers have not been measured yet.

---

## 12. Hard rules for any AI editing this repo (from `CLAUDE.md`)

1. **Ownership.** Edit only files in your user's column (`CLAUDE.md` table). `docs/` and `domain/enums.py` (by block), `domain/__init__.py`, `pyproject.toml` and `requirements.txt` are shared.
2. **Dependency direction.** `samg.domain` ← everything. Never import another owner's private module. Use the public functions in `THREE_PERSON_PLAN.md` §2.
3. **Seeds.** Every random source takes an explicit seed or RNG. No unseeded `random.*` or `np.random.default_rng()`.
4. **Learning gate.** Only an `EpisodeStatus.ADMITTED` episode with an `ACP_RECOMPUTED` reward may update a protected policy. A protected `observe()` must call `LearningEvent.require_protected_eligible()`.
5. **A signature proves authorship, not truth.** Never copy a claimed reward into a protected reward.
6. **Signed bytes.** Signatures cover `event.signed_payload_bytes()` only (canon-v1). Never build an equivalent dict by hand.
7. **`Vulnerable*`** is for Experiment C only and never default wiring. `World.create` enforces the mode pairing.
8. **Errors.** Failures return structured `ReasonCode`s. No `print` for errors and no swallowed exceptions.
9. **Keys.** Private keys stay in `KeyRing` memory. Never persist or log them.
10. **Contract freeze.** After G0, `samg.domain`, enum values, config keys, signed fields, feature order and reward terms change only with a `docs/DECISIONS.md` entry plus updated fixtures. **Do not "fix" a failing contract test by editing the contract.**
11. **Workflow.** Branches are `a/…`, `b/…`, `v/…`, and `main` stays green. Write tests first. `pytest` must pass before a PR. The team's commit convention has no AI attribution lines.
12. **Experiments.** Tune on dev only. Freeze and hash `config/experiment.yaml` before the held-out run, and never retune after it. Copy results tables only from runner output.

---

## 13. Common questions, with short accurate answers

- **"Is this controlling real robots?"** No. Everything is simulated, including the agents, the witness and the attacker.
- **"Why three topologies?"** Brief §5.3. They span centralised, role-cell and peer-to-peer coordination. Each is a deterministic template in `topology/templates.py`.
- **"Why does the topology matter?"** It decides hop counts. Hops set the handoff cost (`h0 + h1·hops`), handoff delay (2 min per hop), message-loss risk and feasibility. The number of links per agent also slows that agent down (D031). CP-SAT therefore produces different plans per topology, which tests assert.
- **"Judge mission handoff example?"** Under HIERARCHICAL the hub is A0. A handoff between two non-hub agents is 2 hops, so it costs `1.0 + 2×0.5 = 2.0` with a delay of 240 000 ms. Dependency density `d = 7/28 = 0.25`.
- **"Why LinUCB and not deep RL?"** There are 3 arms, a 5-dimensional context and short training streams. LinUCB is interpretable and sample-efficient, and the brief excludes other learners (§2.2).
- **"What stops a compromised agent from lying?"** Its claim is AUTHENTICATED (the signature is real) but then DISPUTED against the witness record. The protected learner uses only the reward the ACP recomputed from witness outcomes. A claimed reward is never used, even when corroborated.
- **"What if the witness lies?"** Out of scope. The trust assumption is an honest simulated witness (brief §8.5). Say this openly.
- **"What about replay?"** The dedupe key `(mission_id, epoch, signer_id, seq)` makes replayed events DUPLICATE, and a re-offered episode is refused with DUPLICATE_EPISODE (`replay_events`).
- **"Does LinUCB beat the baselines?"** Not measured yet. Experiments A/B are running (item 11). The landscape analysis (R8) predicts small margins, about 0.008 reward.
- **"Why is it deterministic?"** Seeded scenario, keys, simulator and policy warm-up; CP-SAT with one worker and seed 0; and no wall-clock values in the output.
- **"Why CP-SAT and not a neural solver?"** CP-SAT is exact and constrained (D003). A neural baseline after Luttmann & Xie (ICAPS 2024) is deferred and local-only, and at SAMG's size even the paper reports only parity (D022, R4).
- **"What happens when a topology is infeasible?"** It is not offered to the policy (D030). The reason is recorded as `ALLOCATION_INFEASIBLE` or a structural reason, and infeasibility is reported per topology.
- **"What is greedy for?"** It is the deterministic fallback when CP-SAT is disabled or finds no incumbent in time. Its use is recorded in `plan.fallback_used` and must be disclosed.

---

## 14. What NOT to claim

- That LinUCB outperforms the fixed baselines or UCB1. **Not measured yet.** Claim it only from `docs/RESULTS*.md` with CIs, and only where the §12.10 checklist marks it supported.
- That the demo's Section 2 shows learning works in general. It is an illustration with `alpha = 0.3` on 30 missions, not a held-out result.
- That the demo's attack table is the Experiment C result. The full harness (frozen attack config, FRR over clean missions, held-out metrics) is item 15.
- That SAMG is "secure" in a real-world sense. It is a simulation. Key theft, a dishonest witness, Byzantine evidence sources, DoS and side channels are out of scope.
- That signatures prove reports are true.
- Any neural allocator result, or that a neural allocator is part of the MVP (D022, D029).
- That the cost parameters (`link_cost`, `span_overhead`, `h0/h1`) are empirically calibrated. They are predeclared modelling choices and need sensitivity analysis. D021 and D032/D033 are still *proposed*.
- Large effect sizes. R8 margins are about 0.008 reward, so results will be parameter-sensitive.
- That the Streamlit dashboard exists. It is in progress, and the CLI is the fallback.
- Anything about the brief's exact wording, unless the user supplies the brief.
