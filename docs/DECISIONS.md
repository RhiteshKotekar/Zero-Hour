# Architecture Decisions

These lightweight ADRs establish the initial guardrails. Add a dated decision rather than silently changing an agreed cross-team contract.

## D001 — Use a modular Python monolith

**Decision:** Keep all components in one Python package with explicit module boundaries and a local SQLite store.

**Why:** The project is a hackathon simulation. Independent packages give the four developers clear ownership without deployment, API, or infrastructure overhead.

## D002 — Make the topology graph operational

**Decision:** Represent coordination with a directed NetworkX graph and derive allocation feasibility, path delay, reliability, and coordination cost from it.

**Why:** A visual-only graph would not test adaptive organisational structure. This connects each topology decision to measurable performance effects.

## D003 — Prefer CP-SAT with a deterministic greedy fallback

**Decision:** Use OR-Tools CP-SAT for constrained allocation and provide a documented deterministic greedy fallback.

**Why:** CP-SAT gives a credible constrained optimiser; the fallback keeps demonstrations operational under infeasibility, unavailable solver dependencies, or strict time limits without hiding constraint violations.

**Reaffirmed by D022 (2026-11-14):** CP-SAT is the allocator for the hackathon MVP and for Experiments A–C. A neural allocator may be added later, only as an optional, local-only comparison baseline. It does not replace CP-SAT or greedy.

## D004 — Separate signed claims from validated outcomes

**Decision:** `AgentReport` is never a learner input. ACP produces `ValidationDecision`; only `VALID` decisions can yield a protected `LearningEvent`.

**Why:** Digital signatures authenticate origin but cannot prove report truth. The separation makes Experiment 2 meaningful and testable.

**Extended by D026 (2026-11-14):** if the deferred neural baseline is ever enabled, the same separation applies to its training data and model checkpoints.

## D005 — Persist audit events locally and append-only

**Decision:** Store run inputs, reports, evidence, validation decisions, and learning events in SQLite as append-only records.

**Why:** A hackathon needs simple, inspectable persistence and reproducibility. Event history makes it possible to explain why a policy did or did not learn.

## D006 — Use Pydantic at all cross-package boundaries

**Decision:** Cross-package payloads are Pydantic models owned by `samg.domain`; NetworkX graphs and solver objects are wrapped behind domain-facing results.

**Why:** Explicit validation prevents parallel workstreams from drifting in field names, enums, units, and serialisation.

## D007 — Record seeds, schemas, and solver configuration

**Decision:** Every run persists deterministic seeds, feature/reward versions, policy hyperparameters, topology eligibility, and solver settings.

**Why:** Learning and optimisation demos are not credible if their outcomes cannot be reproduced or explained.

## D008 — Keep SQLAlchemy optional at first

**Decision:** Use `sqlite3` with parameterized queries for the initial narrow repository layer. SQLAlchemy remains an approved dependency if repository complexity warrants typed mappings later.

**Why:** It minimizes ceremony while staying within the requested technology stack. A switch must retain the documented schema and append-only semantics.

## D009 — Three-person team (2026-11-14)

**Decision:** Dev A (mission, graph, allocation, simulation, performance experiments), Dev B (events, assurance, witness, learning, persistence, orchestration, attack experiments) and a Validator, per `docs/THREE_PERSON_PLAN.md`. Supersedes the ownership map in `IMPLEMENTATION_PLAN.md`.

**Why:** The whole security-critical path (report → ACP → admission → policy update) gets a single owner; the two devs share only `samg.domain` and config files.

## D010 — Context features `ctx-v1 = [1, d, h, r, a]` (2026-11-14)

**Decision:** Intercept, dependency density, capability heterogeneity (mean pairwise Jaccard distance), resource scarcity, availability ratio (brief §6.1). Replaces the 10-feature schema in `EXPERIMENTS.md`.

**Why:** Fewer, interpretable features suit LinUCB with a short training stream.

## D011 — Baseline set (2026-11-14)

**Decision:** P0-H/F/D fixed topologies, P1 best-fixed-on-training, P2 context-free UCB1, P3 LinUCB (brief §12.1).

**Why:** P1 and P2 separate the value of adaptation from the value of context.

## D012 — Graph handoff cost `c(a,b) = h0 + h1·hops` (2026-11-14)

**Decision:** Handoff cost between assignees is 0 for the same agent, `h0 + h1·hops` if a coordination path exists, infeasible otherwise (brief §5.4). Per-edge latency/reliability are optional extras, not objective terms.

**Why:** Simple, hand-checkable, and still makes topology change the allocation objective.

## D013 — Reward `0.65C + 0.15(1−T) + 0.10(1−R) + 0.10(1−H)` (2026-11-14)

**Decision:** Brief §7.2 reward, weights in `config/reward.yaml`. Replaces the 5-term reward in `ARCHITECTURE.md`.

**Why:** Completion dominates; time, resources and handoff overhead are penalties. ACP recomputes it from admitted outcomes.

## D014 — Evidence = signed witness events + task-state machine (2026-11-14)

**Decision:** Independent evidence is a `WitnessEvent` signed by a separate witness identity from simulator task transitions; claims are checked against the task-state machine (brief §8.5, §8.8). Replaces generic `EvidenceArtifact`.

**Why:** Gives evidence a concrete, authenticated, independent source in the simulation.

## D015 — Event and episode statuses (2026-11-14)

**Decision:** Event: `AUTHENTICATED / REJECTED / STALE / DUPLICATE / PROVISIONAL / DISPUTED / CORROBORATED`. Episode: `ADMITTED / PROVISIONAL / REJECTED`. Only `ADMITTED` updates a protected policy. Replaces per-report `VALID / REJECTED / INDETERMINATE`.

**Why:** Separates "is this event authentic and fresh" from "is it corroborated" from "can this mission teach the policy".

## D016 — Freshness by epoch and sequence (2026-11-14)

**Decision:** Primary replay barrier is the mission epoch plus dedupe key `(mission_id, epoch, signer_id, seq)` and event-ID uniqueness. Timestamps are a secondary clock-skew/age check. Replaces timestamp-age + nonce.

**Why:** Deterministic in simulation time and independent of wall-clock behaviour.

## D017 — Experiments A–D (2026-11-14)

**Decision:** A (topology adaptation), B (context value), C (signed-false-report poisoning), D (optional replay/graph patch) per brief §12.

**Why:** Matches the frozen brief; C is the security result.

## D018 — Three dashboard views, CLI fallback (2026-11-14)

**Decision:** Mission Control, Adaptive Evaluation Lab, Security & Attack Lab (brief §15). The CLI is the fallback demo.

**Why:** Each view maps to one claim; the CLI keeps the demo alive if the UI is unstable.

## D019 — Event contract details chosen at G0 (2026-11-14)

**Decision:**
- Canonical encoding `canon-v1` (`samg.domain.canonical`): sorted-key compact UTF-8 JSON; enums as values; aware datetimes → UTC ISO-8601 with microseconds; floats finite, rounded to 9 decimals, `-0.0 → 0.0`. Signed bytes = every event field except `signature`, including a `kind` discriminator (`AGENT_EVENT` / `WITNESS_EVENT`) so agent and witness payloads cannot be confused.
- Simulation keys: Ed25519 seed = `SHA-256("samg-ed25519-v1|{seed}|{identity_id}")`; `key_id = "{identity_id}#{first 12 hex of SHA-256(public key)}"`.
- `LearningEvent.reward_source` (`ACP_RECOMPUTED` / `AGENT_CLAIM`): protected policies require `ADMITTED` and `ACP_RECOMPUTED`; `VulnerableLinUCB` uses `AGENT_CLAIM`.
- `EpisodeRecord.reward` is present iff the episode is `ADMITTED`.
- Identity roles: `AGENT`, `COORDINATOR` (may also sign `GRAPH_PATCH`), `WITNESS`.

**Why:** These are byte-level and gate-level details both devs must agree on before signing or learning code is written; the golden-signature test in `tests/contract/` locks them.

## D020 — Mission/graph contract details chosen at G0, aligned to the shared fixtures (2026-11-14)

**Decision:**
- Dev A's models adopt the field names already used in `tests/contract/fixtures/01–02`: `AgentProfile.capacity` (max tasks per mission), `TaskSpec.duration_ms`, `TaskSpec.priority_weight`, `MissionSpec.deadline_ms`. All simulated time is in milliseconds; the judge scenario's minute values are multiplied by 60 000. `MissionSpec.scenario_id` is optional (fixtures omit it).
- Dev A enums (`CapabilityMatch`, `NodeKind`, `EdgeKind`, `SolverName`, `IneligibilityReason`, `AllocationFailure`) use UPPERCASE values, matching Dev B's enums. `TopologyName` keeps Dev B's values and order.
- `Scenario` bundles `MissionSpec` + agents + optional `permitted_links` (directed NetworkState). A topology may only use an undirected link permitted in both directions; `None` means every pair is permitted.
- Topology builders take a `Scenario`: `build_graph(scenario, topology, costs) -> (TopologyEligibility, CoordinationGraph | None)` and `eligible_topologies(scenario, costs)`. This replaces the `(mission, agents, …)` signature listed in `THREE_PERSON_PLAN.md` §2.
- Hub rule: hierarchical and functional-cell use one hub coordinator = the mission lead if available, else the first coordinator-eligible agent by ID. No hub → `NO_COORDINATOR`. Functional-cell cells are role groups with direct intra-cell links; each cell coordinator links to the hub.
- Context features are emitted as `MissionContext(features=(1, d, h, r, a), feature_schema_version="ctx-v1")`; Dev B's policies consume `features` as the context tuple.

**Why:** Dev B merged the fixtures first; matching them keeps `main` green and makes `test_mission_fixtures_load` pass without regenerating signed fixtures.

## D021 — Per-link maintenance cost in coordination overhead (2026-11-14, proposed)

**Decision:** Coordination overhead `H` = graph-derived handoff cost (`h0 + h1·hops` per cross-agent dependency, D012) **plus** `link_cost` × number of undirected coordination links the topology maintains (`config/topology_costs.yaml`, default 0.25). The same rule applies to every topology. `H` is normalised by `max_coordination_cost` (every dependency at `max_path_hops` plus a full mesh).

**Why:** With hop cost alone, distributed (1-hop direct links) dominates whenever its degree cap does not bind, and functional-cell can never beat hierarchical on the judge mission, so the bandit has nothing context-dependent to learn. A uniform link-maintenance cost is the standard communication-overhead trade-off (more links = more overhead) and is not a per-topology bonus. It must be included in the §12.9 topology-cost sensitivity check and disclosed in the results.

## D022 — Neural allocator is a deferred, optional, local-only comparison baseline (2026-11-14)

**Decision:**

- **Scope.** The hackathon MVP keeps CP-SAT, with the deterministic greedy fallback, as its only allocator (D003). After the hackathon, an optional neural constructive allocator may be added as a **comparison baseline**, following Luttmann & Xie (ICAPS 2024); see [PAPER_ALIGNMENT.md](PAPER_ALIGNMENT.md). It would be a heterogeneous-graph attention encoder (HAM) with a hierarchical decoder, trained with Pa-POMO, in a `samg.nco` package behind the existing `allocation.allocate()` contract as `SolverName.NEURAL_HAM`.
- **Where it runs.** Only on one developer's laptop, which has an Intel Arc XPU. No MVP test, gate, demo or experiment depends on it.
- **Out of scope for the hackathon.** The hackathon deliverable does not contain it, so it needs **no exception** to brief §2.2 or §14.1 rule 9. Multi-agent RL (including the authors' MAHAM follow-up), HMMs, LLMs and the rest of §2.2 remain out of scope for later work too.

**Why:** The paper's method fits SAMG's allocation sub-problem: a composite (task, agent) action, one capability offered by several agents, and capacity limits. It is worth comparing against CP-SAT. But it adds training cost and a new learning component, which the 24-hour brief forbids, and at SAMG's mission sizes the paper predicts parity, not improvement. The team decided that it is post-MVP comparison work only.

## D023 — Heterogeneous graph view derived from the typed mission graph (2026-11-14, deferred with D022)

**Decision:** If the baseline is built, the NetworkX typed graph stays the single source of truth (§5.1, D002). `nco/features.py` derives a deterministic encoder view from it at each decoding step:

- node type *task* and node type *agent*;
- weighted task–agent capability-fit edges;
- agent–agent hop distances in the selected topology;
- task–task `DEPENDS_ON` adjacency;
- a context node.

Rows are ordered by ID and features normalised. No one-hot IDs are used, so the view is size-agnostic.

**Why:** In the paper, the state graph is an encoder input, not a system of record. Deriving it keeps one representation. The paper rejects one-hot encodings because they tie a model to one instance size.

## D024 — HAM encoder with edge-biased self-attention and a task → agent hierarchical decoder (2026-11-14, deferred with D022)

**Decision:**

- **Encoder.** Follow the paper's HAM: type-specific projections, per-type multi-head self-attention, then cross-attention whose scores are multiplied by the task–agent edge weight.
- **Deviation from the paper.** Add intra-type attention biases: `−β·hops` between agents (masked where there is no path) and a dependency bias between tasks. Without them the selected topology never reaches the encoder.
- **Decoder.** Factorise the composite action as `π(t, a | s) = π_T(t | s) · π_A(a | s', t)`. Each sub-policy has its own attention decoder.
- **Masks.** A task is selectable when it is unassigned and all its predecessors are assigned. An agent is selectable when it is available, capable, within capacity and budget, and reachable by a permitted path from the agents of the task's predecessors.
- **Executable graph.** The §12.10 "topology changes the objective or the assignment" test and the `h0 = h1 = 0` ablation must also pass for this allocator.

**Why:** The paper's encoder and decoder ablations (Tables 3–4) favour HAM and hierarchical decoding. SAMG adds precedence and graph reachability, which the paper's problem does not have. These extensions keep "the graph is executable" true for the baseline.

## D025 — Train offline with Pa-POMO, then freeze (2026-11-14, deferred with D022)

**Decision:**

- **Method.** REINFORCE with the Pa-POMO shared baseline: `W` starting actions sampled from the policy without replacement, plus a one-epoch exponential-moving-average warm-up.
- **Data.** Training instances are generated on the fly from the scenario generator's `nco-train` seed range.
- **Reward.** The negative of the allocation objective CP-SAT minimises, `allocation.common.evaluate(...).weighted_total`, with the `config/allocation.yaml` weights and the D021 link cost.
- **Freezing.** One checkpoint is selected on `nco-dev` instances only and frozen by its SHA-256. There are no online or fine-tuning updates. LinUCB and UCB1 remain the only online learners.

**Why:** The paper trains this way (Algorithm 1). A frozen checkpoint behaves as a fixed allocator in the sense of brief §7.1. It also keeps the "one online learner" rule of brief §6.5.

## D026 — Learning-gate invariant restated; model-artefact invariants for the neural baseline (2026-11-14)

**Decision:** INV-05 applies unchanged in the MVP. If the neural baseline is enabled, it is read as "only `ADMITTED` episodes can update persistent *online* policy state (LinUCB, UCB1)". The following invariants then also apply, **only while the baseline is enabled**:

- **INV-10:** allocator training data and rewards come only from the seeded generator and `allocation.common.evaluate`. Agent events, witness events and episodes, admitted or not, are never training inputs.
- **INV-11:** a checkpoint is loaded only if its SHA-256 matches a `FROZEN` registry row and the run manifest, and only with `torch.load(weights_only=True)`.
- **INV-12:** every plan the neural allocator returns passes `allocation.validate_plan` before simulation. A failure falls back to CP-SAT, or to greedy if CP-SAT is unavailable, with a reason code.
- **INV-13:** the `nco-train`, `nco-dev` and `nco-test` seed ranges are disjoint from each other and from the Experiment A splits.

Extends D004. Details are in [SECURITY_MODEL.md](SECURITY_MODEL.md#offline-training-plane-and-model-artefacts-deferred-neural-baseline).

**Why:** An RL-trained solver opens a second route by which data shapes future decisions. These rules close that route before the baseline can exist. Masking is a construction aid, not a proof.

## D027 — Compute and device policy for the neural baseline (2026-11-14, deferred with D022)

**Decision:**

- **MVP.** Nothing in the MVP needs PyTorch, an XPU or the NPU.
- **Hardware.** The baseline runs only on one developer's laptop: Intel Core Ultra 5 125H, Intel Arc iGPU, AI Boost NPU, 15.4 GB RAM, no NVIDIA GPU.
- **Training device.** The XPU is used **only** to train, and optionally benchmark, the baseline: `device="xpu"` with torch 2.15.0+xpu in a separate virtual environment. The project `.venv` keeps CPU torch or no torch at all.
- **Choosing between XPU and CPU.** Models of roughly ≥ 259k parameters use the XPU after a CPU/XPU benchmark. Tiny models use the CPU. For 7k–259k parameters, time both devices.
- **Encoder code.** Plain PyTorch attention, with no PyTorch Geometric, because `GCNConv` fails on XPU at every tested size. A PyG baseline, if ever added, runs on CPU.
- **NPU.** Inference only, through OpenVINO with fixed padded shapes, and optional.
- **Model size.** Recommended `d_h = 128`, `L = 3`, 8 heads (≈ 1.7M parameters). Small fallback `d_h = 64`, `L = 2` (≈ 0.3M).
- **Reproducibility.** Defined at the checkpoint, not at training. Recorded inference runs on CPU with deterministic algorithms and a fixed tie-break, and sampling uses a seeded `torch.Generator`.

**Why:** The paper trained for 4–27 h on an A100-80GB. Deterministic inference from a pinned checkpoint is achievable on this laptop; bitwise-reproducible iGPU training is not. The PyG/XPU failure has been observed on this hardware.

## D028 — The neural baseline sits outside the 24-hour timeline (2026-11-14)

**Decision:** No phase, gate, sync point or fallback rule of the hackathon plan contains neural work. The design, ownership and risks are kept in [THREE_PERSON_PLAN.md "Later: neural allocator baseline (local only)"](THREE_PERSON_PLAN.md#later-neural-allocator-baseline-local-only). That work starts only after the hackathon submission, or after the brief's MVP checklist (§18) is complete.

**Why:** Brief §14 makes the H14 vertical slice and the two main experiments non-negotiable. Keeping the baseline off the timeline removes the risk that it displaces them.

## D029 — Experiments A–C use CP-SAT; Experiment E is optional and local-only (2026-11-14)

**Decision:**

- **Experiments A–C** use CP-SAT, with the greedy fallback disclosed, for every compared policy (brief §7.1).
- **Experiment E** is an optional comparison run later, on the laptop that does the training. It follows the paper's protocol (Tables 3–5):
  - the frozen neural allocator (greedy, sampling ×W and beam decoding) against CP-SAT (time-limited, plus a long-limit best-known reference) and greedy;
  - on `nco-test` instances;
  - measuring objective, gap to the best known plan, runtime, validator pass rate and fallback rate;
  - with an optional mission-size sweep and a decoder ablation.
- **Not in the hackathon.** Experiment E results are not part of the hackathon results tables or demo.

**Why:** The team chose CP-SAT for A–C. The paper's own result at small sizes is parity with an exact solver, so any neural claim must come from a separate measurement (§12.10, §17.1).

## D030 — Topology eligibility includes allocation feasibility (2026-11-14)

**Decision:** A topology is offered to a policy only if it can be built (`eligible_topologies`, unchanged) **and** the allocator finds a feasible plan for it. `samg.allocation.feasible_topologies(scenario, costs, config)` returns the eligible arms, a verdict per arm (new reason `IneligibilityReason.ALLOCATION_INFEASIBLE`, with the allocator's reason codes in `detail`) and the `(graph, plan)` per eligible arm, so orchestration can reuse the plan instead of solving twice. `eligible_topologies` keeps its signature for callers that only need the structural check.

**Why:** After the generator fix (R5 in `WORK_QUEUE.md`), 10/643 scenario×topology pairs passed structural eligibility but had no feasible plan (all DISTRIBUTED, where the degree cap removes a needed path). Offering such an arm makes a policy pay an infeasible outcome it could have avoided. Feasibility is known before execution, so it does not leak outcome information. Brief §12.8 still requires reporting the infeasibility rate: it is now reported per topology as ineligibility, not as a selected-arm failure.

## D031 — Span-of-control cost: agents slow down with each extra coordination link (2026-11-14)

**Decision:** An agent's effective task duration = `duration_ms × (1 + span_overhead × max(0, degree − 1))`, where `degree` = that agent's coordination links in the selected topology. `span_overhead` lives in `config/topology_costs.yaml` (base 0.10, predeclared before any experiment result; 0 disables). The allocator (`AllocationProblem.effective_duration`), both solvers and plan evaluation use it; the simulator should take nominal durations from the plan's assignments.

**Why:** The landscape analysis (WORK_QUEUE R7, design seeds only) showed that without it DISTRIBUTED is best on ~90% of missions with a mean margin of ~0.013 reward, because nothing penalises many links; LinUCB could not beat "always distributed". Span-of-control overhead is the standard organisational trade-off, applied by the same rule to every topology (not a per-topology bonus). Sensitivity (design seeds, 108 missions): span 0 → D 91% / F 4% / H 6%; 0.05 → 80/10/10; **0.10 → 56/16/28**; 0.20 → 35/24/41. At 0.10 the h0/h1 low/high settings flip 2 and 5 missions; removing link cost flips 10. Results must be reported with this sensitivity.

## D032 — Phase 2 evidence-path conventions (2026-11-14, proposed by the integrator)

**Decision:** (No change to signed fields, enum values or fixtures.)
- The simulator records a finished task as `EXECUTING -> REPORTED_COMPLETE`. The witness signs that observation as `EXECUTING -> VERIFIED_COMPLETE`, since only the witness may verify (§8.8). Every other transition is signed unchanged.
- Simulated clock: `issued_at = SIM_BASE_TIME + mission_index days + sim_time_ms`. The ACP's receipt time (`now` for freshness) is the event's simulated issue time. Event ids are `{mission_id}/e{epoch}/{signer_id}/{seq}`, with per-signer `seq` starting at 0 for each mission.
- `validate_event` checks, in order: signature → role allows the event type → freshness → payload schema (a `REWARD_CLAIM` needs a numeric `claimed_reward`) → task-state machine. Only events that pass every check are recorded in the seen-store.
- Corroboration: a task claim is CORROBORATED by the matching witness transition within `evidence_tolerance_seconds`. It is DISPUTED if the witness contradicts it (wrong time, or a FAILED/BLOCKED task), and PROVISIONAL with no witness evidence. A `REWARD_CLAIM` is compared with the ACP-recomputed reward (`metric_relative_tolerance`). If coverage is incomplete, it is DISPUTED when it exceeds the highest reward the witness evidence still permits (tasks witnessed FAILED/BLOCKED are lost; everything else is assumed perfect), and PROVISIONAL otherwise. Even a corroborated reward claim is never used as the reward.
- After-action reporting: one agent files the honest `REWARD_CLAIM`, the one with the most assigned tasks (ties go to the lower agent id). `VulnerableLinUCB` learns from the last *authenticated* `REWARD_CLAIM` in receipt order.
- Protected and vulnerable learners in the attack comparison run in separate SQLite worlds, so their identical event ids never collide in the dedupe barrier.

**Why:** These details sit between Dev A's trace and Dev B's ACP primitives. They had to be fixed for the vertical slice, and fixtures 03–05 pass under them. Dev B may revise them; each one is isolated in `witness/`, `assurance/admission.py` or `orchestration.py`.

## D033 — Reward normalisation used by the integration reward module (2026-11-14, proposed; Dev A to confirm)

**Decision:** `samg.simulation.reward.compute_metrics` serves both the simulator (ground truth) and the ACP (witness-verified outcomes):
- `C` = completed priority weight / total priority weight.
- `T` = makespan / deadline, clipped. Makespan is the latest end of a completed task; with nothing completed, `T = 1`.
- `R` = resource demand of every task that started executing / total budget of the agents the plan assigned, clipped.
- `H` = (handoff cost of planned handoffs whose prerequisite completed + `link_cost` × coordination links) / `max_coordination_cost`, clipped (D012, D021).
- An infeasible plan gets `compute_reward(None)`: the predefined failure outcome (`failure_reward`, `failure_label`). The episode is REJECTED with `INFEASIBLE_PLAN` and never learned from.
- The simulator uses integer milliseconds, so the ACP's reward from witness `sim_time_ms` equals the ground-truth reward exactly when the witness is faithful.

**Why:** `config/reward.yaml` names the ranges but not the edge cases (incomplete missions, which handoffs count, which budget is the denominator). Fixing them once keeps the protected reward and the evaluation oracle on identical arithmetic.

## D036 — Attack configuration lives in `config/security_policy.yaml` (2026-11-15)

**Decision:** An `attack:` section (compromised agent, preferred topology, inflation/deflation, corruption levels, freeze hash) is added to `config/security_policy.yaml`, exposed as the optional, untyped `SecurityPolicy.attack` field. Only `samg.evaluation.experiment_c` reads it (validated by `ExperimentCConfig`); the ACP never does. The attack is tuned on dev seeds only by a predeclared rule (least-chosen topology first, ascending magnitudes, stop at dev S1 shift ≥ 0.2) and then frozen by hash before the recorded run.

**Why:** Experiment C must use a disclosed, frozen, deterministic attack (brief §12.5); keeping it out of the ACP's own policy fields prevents the validator from depending on attacker parameters.

## D037 — Experiment C metric definitions (2026-11-15)

**Decision:** "Admitted to learning": S1 = authenticated claim in an episode updated from the agent claim; S2 = CORROBORATED claim in an applied episode. "Incorrectly blocked": S1 = refused at authentication/freshness; S2 = final REJECTED, STALE, DUPLICATE or DISPUTED (PROVISIONAL counted separately). "Update from an unsupported report": applied reward differs from ground truth by more than 1e-6. Corruption level = fraction of attack-phase missions in a seeded, nested schedule. Follow-up evaluation uses frozen learners. Obsolete-epoch replay is tested by advancing the mission epoch.

**Why:** The security table reports counts with denominators (brief §12.8); these definitions make the counts reproducible.

## D038 — Contextual epsilon-greedy follow-up baseline (2026-11-15)

**Decision:** Add P4 as a follow-up comparator to the frozen P0-P3 experiment. P4 uses ctx-v1 and the per-arm ridge-linear reward model, balanced warm-up, then epsilon-greedy selection over only D030-eligible topologies. It learns only from ADMITTED episodes with ACP-recomputed reward. Epsilon is tuned on dev data only; held-out evaluation averages results across predeclared policy seeds. Its settings and hash are separate in `config/epsilon_greedy.yaml` so the original frozen experiment and reported P0-P3 numbers remain unchanged.

**Why:** A context-free epsilon-greedy sample-mean policy would duplicate UCB1's information limitation. Reusing the contextual linear estimate makes P4 a direct comparison of random exploration against LinUCB's confidence-bonus exploration. The measured comparison and its limits are recorded in `docs/RESULTS.md`; claims remain limited to those results.

## D034 — Experiment A/B sample sizes, dev-tuning rule and freeze (2026-11-15)

**Decision:** `config/experiment.yaml` uses n_dev 40, n_train 120, n_test 60 (chosen from runtime before any result). LinUCB `alpha` is chosen from the predeclared grid {0.1, 0.3, 0.5, 1.0} on the dev split only (20-mission learning stream, 20-mission frozen evaluation block; highest dev-eval mean, ties to the smaller alpha). The config is then frozen (`frozen: true`) with a `# config_hash` comment over experiment + topology-cost + allocation + reward configs; a unit test fails if any hashed config changes without a deliberate re-freeze. The held-out test is run once.

**Why:** Brief §12.2 and §12.7: tune on dev only, freeze before test, never retune after seeing test results.

## D035 — Ablations run on design seeds (2026-11-15)

**Decision:** The §12.9 ablations rerun the full protocol on design seeds ≥ 60 000 with `alpha` kept frozen and P1 re-selected on each setting's own training data. The held-out test split is never used for ablations.

**Why:** Keeps sensitivity analysis from leaking into, or being tuned on, the reported test set.

## D038 — Warehouse digital twin and two optional simulator inputs (2026-11-15)

**Decision:** Add `samg.twin` (layout, A* routing, inventory, orders, task generation, aisle locks, physical replay, adapter) and a "Warehouse Digital Twin" dashboard tab. Orders become SAMG missions; topology selection, CP-SAT allocation, execution, witness, ACP and guarded learning are SAMG's unchanged public functions. `simulation.engine.run` gains two optional, default-empty inputs passed through `orchestration.execute_mission` / `run_single_mission`: `task_delays_ms` (physical travel overruns and aisle-congestion waits measured by the warehouse replay, fed back as task delays) and `agent_breakdowns` (a robot breaks down halfway through a task; its later tasks are `BLOCKED: AGENT_DOWN`). `run_single_mission` also accepts a precomputed `feasible` result to avoid solving twice. Replanning after failures runs the not-witness-verified tasks as a new SAMG mission with failed robots unavailable.

**Why:** The demo needs congestion and robot failures to affect SAMG's timing, reward and witness evidence rather than being drawn on top of it. Defaults keep every existing run byte-identical (tested). Config lives in `config/twin.yaml` (`twin-v1`).

## D039 — Next.js control center over a live SAMG twin server (2026-11-15)

**Decision:** The primary judge-facing UI is a Next.js app (`web/`) with a React Three Fiber 3D warehouse, fed by a FastAPI server (`samg.api`) that runs live `samg.twin` sessions: a server-side simulation clock, order arrivals, SAMG planning waves, time-anchored failure injections and WebSocket state streaming. The Streamlit dashboard stays as the research/secondary UI. `samg.twin` (this branch) and `samg.warehouse` (teammate, Streamlit views) coexist; consolidation is a follow-up. See `docs/CONTROL_CENTER_PLAN.md`.

**Why:** A browser-native 3D control center needs a live state stream and two-way controls that Streamlit's rerun model cannot provide; keeping SAMG decisions in Python keeps the frontend a digital twin rather than a second decision engine.

## D041 — Mission model v2: coordination can change outcomes (2026-11-15, opt-in)

**Decision:** Three rules, applied identically to every topology and enabled only through `TopologyCostConfig.with_model_v2()` (`simulation_model`, absent = model v1): (1) each handoff hop is lost with probability 0.05 and gets one retry (`handoff_max_attempts = 2`); a fully lost handoff blocks the dependent task, which ends FAILED, and blocks its dependents; (2) work finishing after `deadline_ms` does not count in completion C, and v2 scenarios use a deadline of 1.25 × the critical path (`generate_scenario(..., deadline_factor=1.25)`, tagged `gen-v1-deadline1.25`); (3) intermediate agents relay one message at a time, served in plan order. Values were fixed before any v2 result. Model v1 stays the default: the CLI demo output and the warehouse twin's 3D state are byte-identical with v2 off, and frozen config hashes are unchanged (`config_hash` skips absent optional sections). The allocator does not anticipate loss or queueing; plan versus reality is part of the model. No evidence-gate change was needed: blocked tasks already end FAILED, a terminal state the ACP admits.

**Why:** Under v1 every topology completes every mission (C = 1.000), so reward gaps stay below 0.01 and adaptive selection cannot show an advantage (R11). v2 lets communication structure affect whether work gets done. v1 results (`RESULTS.md`, `RESULTS_SECURITY.md`) remain published unchanged.
