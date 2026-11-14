# SAMG Architecture

## Purpose and boundary

SAMG is a modular monolith for **controlled, repeatable mission simulations**. It evaluates whether adapting the coordination topology improves outcomes and whether validating evidence prevents poisoned learning. It is not a real-world command, robotics, or communications system.

The architecture has two deliberately separate planes:

```text
Mission execution plane
  context -> topology decision -> graph -> allocation -> simulated outcome

Assurance and learning plane
  signed report + independent evidence -> ACP decision -> persisted event -> permitted update
```

The learner never accepts a report directly. The ACP is the only writer permitted to emit a learning-eligible outcome.

A third, offline training plane exists only for the deferred neural allocator baseline (D022). It is not part of the MVP; see [Deferred: neural allocator baseline](#deferred-neural-allocator-baseline-optional-local-only).

## Module boundaries

| Package | Owns | Public input → output | Must not own |
| --- | --- | --- | --- |
| `domain` | Pydantic models, enums, validation rules, stable identifiers | specifications and value objects | algorithms, database sessions, UI |
| `topology` | NetworkX graph construction, topology feasibility, path-derived costs | `MissionSpec`, agents, network state, topology → `CoordinationGraph` | task assignment decisions |
| `allocation` | CP-SAT model, greedy fallback, allocation explanation | mission, graph, availability → `AllocationPlan` | reward or report validation |
| `nco` *(deferred, optional, local-only; D022)* | Neural allocator baseline: allocation MDP, heterogeneous graph view, HAM encoder + hierarchical decoder, Pa-POMO training, checkpoint registry | generator instances → frozen checkpoint; scenario + graph → candidate plan | agent reports, episodes, ACP decisions, LinUCB state. Not created for the MVP. |
| `simulation` | deterministic scenario sampling, execution, ground truth, reward | mission, graph, plan, seed → `MissionOutcome` | signature verification or LinUCB state |
| `assurance` | keys, signed report verification, authorization, freshness, independent evidence validation | report, evidence, mission context → `ValidationDecision` | selection policy or simulation rules |
| `learning` | LinUCB selection and gated observation | context → decision; validated outcome → state update | report parsing or evidence gathering |
| `persistence` | SQLite schemas and repositories for append-only run records | domain events ↔ local storage | business-rule decisions |
| `dashboard` | Streamlit/Plotly read models and experiment controls | persisted runs → views | solver, validator, or direct SQL writes |

`domain` may be imported by every package. Peer packages communicate through domain contracts, not each other's private implementation details. A small future `application`/orchestration module may compose the public interfaces; it should contain no domain algorithm.

## Mission execution path

1. A scenario generator creates a validated `MissionSpec`, `AgentProfile` set, and `NetworkState`, using a recorded seed.
2. A baseline selector or LinUCB policy chooses a `TopologyName` from only the feasible options.
3. `TopologyBuilder` constructs a directed `networkx.DiGraph` with agents as nodes and permitted coordination paths as edges.
4. `TaskAllocator` solves a feasible task-to-agent assignment. CP-SAT is preferred; the deterministic greedy allocator is used when CP-SAT returns no feasible solution, is unavailable, or reaches its configured time limit without a feasible incumbent. The MVP and Experiments A–C use only CP-SAT with this fallback (D029).
5. `MissionSimulator` executes the allocation against the same graph and returns ground-truth timing, resources, failures, and a normalized reward.
6. Simulated agents produce signed reports. The simulator can make selected, authenticated agents report false values for Experiment 2.
7. ACP independently validates each candidate learning report and persists its decision.
8. The protected learner observes only `ValidationStatus.VALID` decisions. The vulnerable comparison learner intentionally observes signed claims without the evidence gate.

## The coordination graph is executable

`CoordinationGraph` wraps a `networkx.DiGraph`; it is not a drawing model. Every edge has at least these attributes:

| Attribute | Meaning | Used by |
| --- | --- | --- |
| `allowed` | Whether this directed coordination transfer is permitted | feasibility checks |
| `latency_ms` | Nominal transfer delay | dependency scheduling and simulator |
| `reliability` | Probability-like success factor in `(0, 1]` | risk/expected reward |
| `coordination_cost` | Resource cost of traversing the edge | allocator objective and simulator |
| `channel` | Optional link type / policy label | audit and dashboard |

For every cross-agent task dependency, allocation computes the directed shortest permitted path from the predecessor's assignee to the successor's assignee. The path's summed latency and cost, and compounded reliability, are included in the schedule and objective. No path makes that assignment infeasible. The simulator reuses the same path semantics to produce delay or communication-failure effects.

Topology construction uses the current `NetworkState` as the physical/policy limit; a topology can only enable a subset or structured routing of available links.

- **Hierarchical:** one eligible, available agent is designated coordinator. Coordination between non-coordinators routes through it; centrality may add queue/load penalties.
- **Functional-cell:** compatible agents are partitioned into named cells, each with a coordinator. Intra-cell coordination is direct or coordinator-mediated; cross-cell dependency paths pass through the relevant cell coordinators.
- **Distributed:** all currently permitted direct links in `NetworkState` may be used; no synthetic central relay is introduced.

If a requested topology cannot designate required coordinators or yields no viable path for mandatory dependencies, it is excluded before policy selection and its reason is recorded.

## Core interfaces to implement

Names below are the initial contracts. Concrete parameter types belong in `domain.models`; implementations can add keyword-only tuning parameters but must preserve these semantics.

```python
class TopologyPolicy(Protocol):
    def select(
        self, context: MissionContext, eligible: Sequence[TopologyName]
    ) -> TopologyDecision: ...

    def observe(self, event: LearningEvent) -> None: ...

class TopologyBuilder(Protocol):
    def build(
        self,
        mission: MissionSpec,
        agents: Sequence[AgentProfile],
        network: NetworkState,
        topology: TopologyName,
    ) -> CoordinationGraph: ...

class TaskAllocator(Protocol):
    def allocate(
        self,
        mission: MissionSpec,
        graph: CoordinationGraph,
        availability: AgentAvailability,
    ) -> AllocationPlan: ...

class MissionSimulator(Protocol):
    def run(
        self,
        mission: MissionSpec,
        graph: CoordinationGraph,
        plan: AllocationPlan,
        seed: int,
    ) -> MissionOutcome: ...

class AssuranceValidator(Protocol):
    def validate(
        self,
        report: AgentReport,
        evidence: Sequence[EvidenceArtifact],
        context: ValidationContext,
    ) -> ValidationDecision: ...
```

`TopologyPolicy.observe` receives a `LearningEvent` only after an orchestration guard has checked `event.validation_status is VALID`. The protected implementation must also defensively reject an ineligible event; enforcement in two places prevents accidental bypass during integration.

## Allocation model

The initial CP-SAT formulation uses a binary variable `x[task, agent]`. It enforces:

- exactly one assignee for every mandatory task;
- required capability coverage and authorization;
- agent availability, capacity, resource budgets, and optional task windows;
- task dependency precedence, including graph-derived coordination transit time;
- reachable coordination paths for cross-agent dependencies;
- optional anti-colocation or role-separation constraints from the mission.

The objective minimizes a documented weighted sum of task execution time, coordination path cost, expected communication risk, load imbalance, and unserved optional-task penalty. Weights are part of the scenario configuration and are persisted with every run.

The fallback must be deterministic: sort tasks by mandatory-first, then dependency depth, scarcity of capable agents, and ID; sort agent candidates by incremental objective cost, remaining capacity, and ID. It must return the same `AllocationPlan` for the same inputs. It may report infeasibility; it must not silently violate constraints.

## LinUCB policy

There is one arm per topology. With a versioned, normalized feature vector `x` and arm `a`:

```text
A[a] starts at lambda * I
b[a] starts at 0
theta[a] = solve(A[a], b[a])
score[a] = theta[a]^T x + alpha * sqrt(x^T solve(A[a], x))

on an eligible validated reward r:
  A[a] <- A[a] + x x^T
  b[a] <- b[a] + r x
```

Tie-breaking is deterministic by `TopologyName`. Store `feature_schema_version`, `alpha`, `lambda`, chosen arm, score vector, context vector, and policy RNG seed with each decision. The baseline policies use the same topology eligibility filtering.

## Reward and reproducibility

The simulator produces a versioned reward in `[0, 1]`. The starting formula is configurable, but a run must persist its exact weights:

```text
reward = clamp(
    0.45 * mandatory_completion
  + 0.20 * deadline_adherence
  + 0.15 * resource_efficiency
  + 0.10 * communication_reliability
  + 0.10 * coordination_efficiency,
  0, 1
)
```

An infeasible plan, failed mandatory task, or validation rejection is represented explicitly; it is never disguised as a normal success reward. Scenario seed, policy seed, solver settings, package version, reward schema, and feature schema must be persisted so a run is replayable.

## Non-negotiable invariants

1. Agent and task identifiers are immutable and globally unique within an experiment.
2. A signature proves that a registered key signed exact bytes; it does not establish truth.
3. An ACP `VALID` decision requires authorization, a valid signature, freshness, and independent evidence that supports the claimed outcome.
4. Only a valid decision can produce a protected `LearningEvent`; rejected or indeterminate reports remain auditable but never alter protected LinUCB matrices.
5. The vulnerable learner is intentionally unsafe only within the Experiment 2 comparison path and must be clearly named and isolated.
6. Graph paths influence both allocation and simulation, and graph-derived values are persisted in the allocation explanation.
7. All random sources and solver settings are explicit and recorded.

## Deferred: neural allocator baseline (optional, local-only)

**Not part of the hackathon MVP.** Nothing above depends on this section. It records the design for a later comparison baseline that follows [Luttmann & Xie (ICAPS 2024)](PAPER_ALIGNMENT.md) (D022–D029). The baseline is trained and evaluated only on one developer's laptop with an Intel Arc XPU, and it is compared with CP-SAT in the optional Experiment E. Experiments A–C always use CP-SAT.

### Planes

```text
Offline training plane (later; never during an experiment)
  seeded generator instances (nco-train) -> allocation MDP -> Pa-POMO training
     -> candidate checkpoint -> dev selection -> FROZEN checkpoint (SHA-256) -> neural allocator
```

The training plane has no input from reports, witness events or episodes (INV-10). The execution plane consumes only a frozen, hash-matched checkpoint (INV-11).

### Design summary

- **State.** A heterogeneous graph view derived from the typed graph (D023):
  - *task* nodes: duration, demand, priority, `mandatory`, `reward_critical`, degree, depth, assigned flag;
  - *agent* nodes: remaining capacity and budget, availability, `can_coordinate`, next-free time, load;
  - task–agent capability-fit edge weights;
  - agent–agent hop distances in the selected topology;
  - task–task dependency adjacency;
  - a context node: last assignment, makespan so far, fraction assigned.
- **Action and decoder.** A composite `(task, agent)` action, decoded hierarchically as `π_T(t | s) · π_A(a | s', t)` [P Eq. 18] (D024). Masks enforce:
  - task readiness: every predecessor is assigned;
  - capability and authorisation;
  - availability;
  - capacity and resource budget;
  - reachability of a permitted coordination path from every predecessor's agent.

  Reaching a state with no selectable task while tasks remain unassigned returns an explicit infeasible result.
- **Transition.** Deterministic. The task starts at the later of its predecessors' end plus handoff delay and its agent's free time. Agent capacity, budget and free time are then updated.
- **Reward.** The negative of `allocation.common.evaluate(...).weighted_total`, the same objective, weights and link cost (D021) that CP-SAT minimises, so gaps are directly comparable.
- **Encoder.** HAM [P: Encoder]: type-specific projections, per-type multi-head self-attention, and cross-attention scaled by the edge weight (`α'_ij · e_ij`). It adds intra-type edge biases for hops and dependencies (a documented deviation, D024). It is written in plain PyTorch, with no PyTorch Geometric (D027).
- **Training.** Pa-POMO [P: Alg. 1], run offline on `nco-train` generator seeds and then frozen (D025).
- **Inference.** Greedy (argmax), seeded sampling with `W` candidates, or beam search. The candidate plan with the lowest objective is chosen, ties broken by `(task_id, agent_id)` order, and then validated. Recorded runs infer on CPU for determinism (D027).
- **Not adopted from the paper.** Tours, the depot and split deliveries: SAMG assigns each task exactly once.

### The graph stays executable

The selected topology reaches the baseline through its masks (no path → masked), its encoder input (agent–agent bias `−β·hops`) and its reward (`H(A, G_O)`). The §12.10 "changing topology changes the objective or the assignment" test and the `h0 = h1 = 0` ablation are repeated for it.

### Contracts (added only when the baseline is built)

`NeuralAllocator` follows the public `allocate(scenario, graph, costs, config)` signature (D020), so orchestration does not change.

```python
class AllocationEnv(Protocol):            # nco/env.py — the paper's MDP adapted to SAMG
    def reset(self, scenario: Scenario, graph: CoordinationGraph) -> NcoState: ...
    def task_mask(self, state: NcoState) -> BoolTensor: ...                 # [T]
    def agent_mask(self, state: NcoState, task_id: str) -> BoolTensor: ...  # [A]
    def step(self, state: NcoState, task_id: str, agent_id: str) -> NcoState: ...  # deterministic
    def reward(self, state: NcoState) -> float: ...  # -evaluate(...).weighted_total; terminal only

class PolicyNetwork(Protocol):            # nco/model.py — HAM encoder + hierarchical decoder
    def forward(self, obs: HeteroObservation) -> tuple[Logits, Logits]: ...

class CheckpointRegistry(Protocol):       # nco/checkpoint.py
    def load_frozen(self, checkpoint_sha256: str) -> PolicyNetwork: ...  # INV-11

def allocate_neural(scenario, graph, costs, config) -> AllocationPlan: ...
    # allocation/neural_adapter.py: decode -> validate_plan -> fallback to CP-SAT, then greedy (INV-12)
```

### Reproducibility

A run that uses the baseline also persists:

- the checkpoint SHA-256 and the model and training config;
- the decode strategy, decode seed and inference device;
- the torch version.

Replay is guaranteed for the same checkpoint and the same inputs on CPU. Bitwise-reproducible *training* on XPU is not promised (D027).

### Additional invariants (apply only when the baseline is enabled; D026)

8. Only admitted, validated outcomes update persistent *online* policy state (LinUCB, UCB1). The frozen neural allocator is never updated online (INV-05 restated).
9. Allocator training data and rewards come only from the seeded generator and `allocation.common.evaluate`. Reports, evidence and episodes are never training inputs (INV-10).
10. A checkpoint is loaded only if its SHA-256 matches a frozen registry entry and the run manifest, and only with `weights_only=True` (INV-11).
11. Every neural plan passes `allocation.validate_plan` before simulation. Masks are not trusted on their own (INV-12).
12. The `nco-*` seed ranges are disjoint from each other and from the experiment splits (INV-13).
