# Four-Developer Implementation Plan

The goal is to let four developers work in parallel without competing for the same files. Public model changes require agreement because they affect every workstream.

> **Status:** superseded for team structure by [THREE_PERSON_PLAN.md](THREE_PERSON_PLAN.md) (D009). A deferred, optional, local-only neural allocator baseline (D022–D029, [PAPER_ALIGNMENT.md](PAPER_ALIGNMENT.md)) is mapped onto this plan's roles in [the addendum](#addendum--deferred-neural-allocator-baseline-post-hackathon-local-only). It is not part of any milestone below.

## Ownership map

| Developer | Owns | Primary deliverables | Integration contract |
| --- | --- | --- | --- |
| A — Domain & topology | `domain/`, `topology/` | Pydantic contracts, topology eligibility, NetworkX builders, path-cost API | Supplies `CoordinationGraph` and topology feasibility reason codes. |
| B — Allocation | `allocation/` | CP-SAT formulation, deterministic greedy fallback, allocation explanation | Consumes mission + graph; returns `AllocationPlan` only. |
| C — Simulation & learning | `simulation/`, `learning/` | seeded scenario generator, execution/reward, LinUCB, fixed policies, experiment runners | Consumes plan/outcome contracts; protected update accepts `LearningEvent` only. |
| D — Assurance, persistence & dashboard | `assurance/`, `persistence/`, `dashboard/` | Ed25519 registry/ACP, SQLite repositories, Streamlit experiment views | Emits `ValidationDecision`, persists all events, reads rather than mutates learning state from UI. |

The repository-level docs, dependency file, and shared contract fixtures are jointly owned. One person should act as release integrator per milestone, but module owners review changes to their published interfaces.

## Milestones

### M0 — Contracts and developer setup

**Exit criteria:** package installs; `pytest` discovers tests; `docs/DATA_MODEL.md` models exist as imports; all five contract fixture files exist; schema/signature byte format has one agreed implementation.

- A implements domain enums/models and a graph-free validator for mission dependency cycles.
- B writes allocation test cases against contract fixtures and the `TaskAllocator` protocol, without waiting for the solver.
- C implements fixed policy and LinUCB unit tests against `MissionContext`/`LearningEvent` fixtures.
- D implements identity registry/report canonicalization tests and SQLite migration/connection setup.

### M1 — Independently testable vertical slices

**Exit criteria:** each owner can run a focused test suite with fixture data.

- A: hierarchical, functional-cell, and distributed graphs produce documented paths and ineligibility reasons.
- B: CP-SAT returns a feasible plan for the reachable fixture; fallback returns the same deterministic assignment repeatedly; unreachable dependency assignment is rejected.
- C: simulator generates a seeded ground-truth outcome and LinUCB update math is tested on a small known matrix.
- D: valid/false/stale report fixtures result in valid/rejected/indeterminate ACP decisions and append-only database records.

### M2 — Protected mission path

**Exit criteria:** one deterministic end-to-end mission runs:

```text
scenario -> decision -> graph -> allocation -> outcome -> report/evidence
         -> validation -> persistence -> (valid only) learner update
```

The release integrator writes this in `tests/integration/`. It must prove that a validly signed but evidence-contradicted report changes the vulnerable learner but leaves protected LinUCB matrices unchanged.

### M3 — Experiment and dashboard polish

**Exit criteria:** both experiment manifests are reproducible, metrics are charted, and the README quick-start works from a clean environment.

- Run Experiment 1 against the predeclared scenario matrix and compare all fixed baselines.
- Run Experiment 2 at configured corruption levels and evaluate on clean holdout scenarios.
- Dashboard displays aggregate metrics, topology selection, validation reason counts, and a single-run audit trail.

## File and interface rules

1. Do not import a peer package's internal module. Import only `samg.domain` models and documented protocols/results.
2. Do not change an enum value, signed field, feature ordering, reward term, or SQLite column meaning without updating the relevant documentation, fixtures, and `DECISIONS.md`.
3. Keep a module's unit tests next to its owner area; place only true cross-module paths in `tests/integration/`.
4. All code paths that use randomness receive an explicit seed/RNG. No module creates an untracked global random generator.
5. Optimisation and simulation return structured failures/reason codes; they do not encode failure by printing or swallowing exceptions.
6. Dashboard code does not access private keys, decide validation, or mutate a policy directly.

## First integration backlog

1. Implement `domain.models` and create the five contract fixtures.
2. Implement `TopologyBuilder` and a minimal `CoordinationGraph` path API.
3. Implement CP-SAT assignment for mandatory tasks plus graph path constraints; add fallback.
4. Implement one seeded simulator scenario and the versioned reward calculation.
5. Implement report signing, independent evidence, ACP validation, and append-only persistence.
6. Wire the protected and vulnerable experiment paths, then add charts only after raw data is persisted.

This order gives each developer a meaningful independent target and reaches the security-critical learning gate before UI polish.

## Addendum — deferred neural allocator baseline (post-hackathon, local-only)

This addendum is optional and comes after M3. It is a comparison baseline for CP-SAT, following Luttmann & Xie (ICAPS 2024); see [PAPER_ALIGNMENT.md](PAPER_ALIGNMENT.md) and D022–D029. It is trained only on one developer's laptop, which has an Intel Arc XPU. M0–M3 and both main experiments use CP-SAT with the greedy fallback.

| Developer | Additional ownership | Deliverables |
| --- | --- | --- |
| A — Domain & topology | `SolverName.NEURAL_HAM`, extended `AllocationPlan` fields (new DECISIONS entry); `nco/features.py` | Heterogeneous graph view (D023), derived from `CoordinationGraph` |
| B — Allocation | `allocation/validate.py`, `allocation/neural_adapter.py`, `nco/env.py` | Plan validator, allocation MDP with masks (D024) built on the existing `allocation.common.evaluate`, fallback wiring (INV-12) |
| C — Simulation & learning | `nco/model.py`, `nco/train.py`, `nco/decode.py` | HAM encoder + hierarchical decoder; Pa-POMO training on the XPU after a CPU/XPU benchmark (D025, D027); Experiment E runner |
| D — Assurance, persistence & dashboard | `nco/checkpoint.py`; `model_checkpoints`, `nco_training_runs`, `allocator_evaluations` tables | Checkpoint integrity (INV-11) and the provenance import check (INV-10) |

The later steps run in this order:

1. **L1:** env masks match the fixture oracle; the model forward and backward pass runs on the chosen device; a tampered checkpoint is refused.
2. **L2:** training is capped at about 3 h; one checkpoint is frozen on `nco-dev`, with 100 % validator pass and mean gap ≤ 5 %.
3. **L3:** optional Experiment E, run locally.

Rule additions: no PyTorch Geometric; no `torch.load` without `weights_only=True`; nothing under `nco/` imports persistence or assurance code.
