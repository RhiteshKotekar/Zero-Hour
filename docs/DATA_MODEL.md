# Shared Data Model and Persistence Contract

This document defines the cross-team contract before implementation. Models should be Pydantic v2 `BaseModel` types with `extra="forbid"`, explicit enums, timezone-aware UTC datetimes, and stable UUID/string identifiers. Public models live in `samg.domain.models`; packages must not create competing copies.

## Domain models

| Model | Required fields | Rules |
| --- | --- | --- |
| `AgentProfile` | `agent_id`, `capabilities`, `resource_capacity`, `can_coordinate`, `authorized_task_classes`, `public_key_id` | Capability/resource values are non-negative; private keys are never included. |
| `AgentAvailability` | `agent_id`, `available_from`, `available_to`, `resource_remaining` | Window and resources are scoped to one mission. |
| `TaskSpec` | `task_id`, `required_capabilities`, `duration_ms`, `resource_demand`, `mandatory`, `dependencies` | Cannot depend on itself; mission validation rejects dependency cycles. |
| `MissionSpec` | `mission_id`, `tasks`, `deadline`, `allocation_weights`, `scenario_id` | Task IDs are unique; referenced dependencies exist. |
| `NetworkState` | `network_id`, `links`, `observed_at` | Links are directed and only describe currently possible physical/policy paths. |
| `NetworkLink` | `source_agent_id`, `target_agent_id`, `latency_ms`, `reliability`, `coordination_cost`, `allowed` | No duplicate directed link per network version; values are bounded and finite. |
| `MissionContext` | `feature_schema_version`, `features`, `mission_id` | Feature vector dimension and ordering come from the schema version. |
| `TopologyDecision` | `decision_id`, `topology`, `eligible_topologies`, `scores`, `context`, `policy_version` | Chosen topology must be eligible; scores are persisted for audit. |
| `CoordinationGraph` | `topology`, `network_id`, `graph_version`, `nodes`, `edges` | Runtime wrapper may contain NetworkX graph; persisted form is JSON-safe nodes/edges. |
| `AllocationPlan` | `plan_id`, `assignments`, `schedule`, `objective_terms`, `feasible`, `solver` | Feasible plans assign every mandatory task once; path explanations are included for cross-agent dependencies. |
| `MissionOutcome` | `outcome_id`, `mission_id`, `plan_id`, `ground_truth_metrics`, `reward`, `seed` | Reward uses a named schema and is derived from simulator ground truth. |
| `AgentReport` | `report_id`, `mission_id`, `agent_id`, `issued_at`, `nonce`, `claim`, `key_id`, `signature`, `schema_version` | Signature covers an exact canonical byte payload. |
| `EvidenceArtifact` | `evidence_id`, `mission_id`, `source_id`, `kind`, `observed_at`, `payload_hash`, `payload` | Source is independent of the reporting agent for learning-grade validation. |
| `ValidationDecision` | `validation_id`, `report_id`, `status`, `reason_codes`, `validated_reward`, `evidence_ids`, `validated_at` | `validated_reward` exists only for `VALID`; rejection reasons are machine-readable. |
| `LearningEvent` | `event_id`, `decision_id`, `topology`, `context`, `reward`, `validation_status`, `outcome_id` | Protected policy accepts only `VALID`; event preserves the decision-time context. |

### Deferred: neural allocator baseline additions (D022–D027)

**Not part of the MVP or the G0 contract freeze.** These models are added only if the optional, local-only neural baseline is built later. The decision is in [DECISIONS.md](DECISIONS.md#d022--neural-allocator-is-a-deferred-optional-local-only-comparison-baseline-2026-11-14). Adding them then needs its own DECISIONS entry and updated fixtures, because `samg.domain` is frozen. `HeteroObservation` and `NcoState` are runtime tensor views inside `samg.nco`. They are never persisted and never cross into the ACP. The remaining models are persisted.

| Model | Required fields | Rules |
| --- | --- | --- |
| `SolverName` (enum) | adds `NEURAL_HAM = "NEURAL_HAM"` next to `CP_SAT` and `GREEDY` (UPPERCASE values per D020) | Existing values are unchanged. |
| `AllocationPlan` (extended) | adds `allocator_version`, `checkpoint_sha256` (null unless neural), `decode_strategy` (`greedy` \| `sampling` \| `beam` \| null), `decode_seed`, `inference_device`, `validator_passed`, `fallback_reason` | `validator_passed` must be true for any plan handed to the simulator. When `fallback_used` is true, `solver` names the solver that produced the final plan and `fallback_reason` names why the neural plan was rejected. |
| `HeteroObservation` | `task_x [T,F_t]`, `agent_x [A,F_a]`, `task_agent_w [T,A]`, `agent_hops [A,A]` (inf = no path), `task_dep [T,T]`, `context [F_c]`, `task_mask [T]`, `agent_mask [T,A]`, `task_ids`, `agent_ids`, `feature_schema_version` (`nco-obs-v1`) | Rows are ordered by sorted ID, and features are normalised to `[0, 1]`. There are no one-hot identities, so the view is size-agnostic. It is derived only from the `Scenario` (D020), the `CoordinationGraph` and the partial plan. |
| `NcoState` | partial assignments, per-agent free time, remaining capacity and budget, step index | It changes only through `AllocationEnv.step`, which is deterministic. |
| `ModelCheckpointRecord` | `checkpoint_id`, `sha256`, `status` (`CANDIDATE` \| `FROZEN` \| `REJECTED`), `model_config`, `training_run_id`, `param_count`, `dev_metrics`, `created_at` | Only one `FROZEN` checkpoint per experiment config hash. The weights file lives under `artifacts/checkpoints/<sha256>.pt`, and its hash is recomputed on load (INV-11). |
| `NcoTrainingRun` | `training_run_id`, `generator_version`, `seed_range` (`nco-train`), `objective_version` (= `config/allocation.yaml` `version`), `train_config` (batch, `W`, lr, steps, warm-up), `device`, `torch_version`, `wall_clock_s`, `started_at`, `finished_at` | It has no field that can reference an `AgentEvent`, `WitnessEvent` or `EpisodeRecord` (INV-10). |
| `AllocatorEvaluation` | `evaluation_id`, `instance_seed`, `split` (`nco-dev` \| `nco-test`), `solver`, `checkpoint_sha256`, `decode_strategy`, `objective`, `gap_to_best`, `runtime_ms`, `validator_passed`, `fallback_used` | Experiment E raw rows. `gap_to_best` is measured against the best valid plan across all solvers for that instance. |

The initial `TopologyName` enum is exactly `HIERARCHICAL`, `FUNCTIONAL_CELL`, and `DISTRIBUTED`. `ValidationStatus` is exactly `VALID`, `REJECTED`, or `INDETERMINATE`; indeterminate is deliberately not valid for learning.

## IDs, times, and serialization

- Use UUIDv4 (or a clearly documented deterministic fixture ID) for externally stored records.
- Store all datetimes in UTC, ISO-8601 with an offset. Compare freshness only after normalization to UTC.
- Records use JSON-compatible primitives. Persist enum values, not Python enum reprs.
- `schema_version`, `feature_schema_version`, `reward_schema_version`, and `policy_version` are mandatory on their respective records. Schema evolution adds a new version; it does not reinterpret historical payloads.
- A signature payload is produced solely by `AgentReport.signed_payload_bytes()`. It contains the schema version, report/mission/agent IDs, issued time, nonce, claim, and key ID in a canonical JSON form (UTF-8, sorted keys, compact separators). Never reconstruct an equivalent ad hoc dict for verification.

## SQLite design

SQLite is the local source of truth for a hackathon run. Enable foreign keys on every connection and use short write transactions. JSON columns are stored as `TEXT` containing canonical JSON; values needed for filtering get first-class columns.

| Table | Key columns | Purpose |
| --- | --- | --- |
| `experiments` | `experiment_id`, `config_json`, `created_at` | Immutable experiment configuration and package/version metadata. |
| `scenarios` | `scenario_id`, `experiment_id`, `seed`, `mission_json`, `agents_json`, `network_json` | Reproducible mission inputs. |
| `topology_decisions` | `decision_id`, `scenario_id`, `topology`, `context_json`, `scores_json`, `policy_version` | Chosen arm and audit data. |
| `allocation_plans` | `plan_id`, `decision_id`, `feasible`, `solver`, `objective_json`, `plan_json` | Solver result and graph-path explanation. |
| `mission_outcomes` | `outcome_id`, `plan_id`, `reward`, `metrics_json`, `seed` | Simulator ground truth. |
| `agent_reports` | `report_id`, `mission_id`, `agent_id`, `issued_at`, `nonce`, `key_id`, `claim_json`, `signature` | Received signed claims. Unique `(agent_id, nonce)`. |
| `evidence_artifacts` | `evidence_id`, `mission_id`, `source_id`, `kind`, `observed_at`, `payload_hash`, `payload_json` | Supporting independent observations. |
| `validation_decisions` | `validation_id`, `report_id`, `status`, `reason_codes_json`, `validated_reward`, `evidence_json` | ACP result; exactly one terminal decision per report. |
| `learning_events` | `event_id`, `decision_id`, `outcome_id`, `validation_status`, `reward`, `applied_at` | Attempted and applied learner observations. |
| `policy_snapshots` | `snapshot_id`, `experiment_id`, `policy_version`, `state_json`, `created_at` | Recoverable LinUCB state checkpoints. |
| `nco_training_runs` *(deferred)* | `training_run_id`, `generator_version`, `seed_range_json`, `objective_version`, `train_config_json`, `device`, `torch_version`, `wall_clock_s` | Only with the neural baseline. Offline allocator training provenance. No foreign key to reports, evidence or episodes. |
| `model_checkpoints` *(deferred)* | `checkpoint_id`, `sha256` (UNIQUE), `status`, `training_run_id`, `model_config_json`, `param_count`, `dev_metrics_json`, `created_at` | Only with the neural baseline. Weights metadata. Weights stay on disk, never in SQLite. A status change is a new row that references the earlier one. |
| `allocator_evaluations` *(deferred)* | `evaluation_id`, `instance_seed`, `split`, `solver`, `checkpoint_sha256`, `decode_strategy`, `objective`, `gap_to_best`, `runtime_ms`, `validator_passed`, `fallback_used` | Only with the neural baseline. Raw results of the optional Experiment E. |

Use append-only records for reports, evidence, validation decisions, and learning events. Corrections are new records that reference superseded IDs; never overwrite an audit event. `learning_events.applied_at` stays null for ineligible protected events, so the dashboard can distinguish attempted poisoning from accepted learning.

## Contract fixtures

Before feature work begins, add these shared JSON fixtures under `tests/contract/fixtures/`:

1. a two-agent, two-dependent-task reachable mission;
2. the same mission with no permitted cross-agent path;
3. a valid signed report with matching independent evidence;
4. a validly signed but false report with contradictory independent evidence;
5. a stale/replayed report.

All teams use these fixtures. They prevent mismatched enum names, timestamps, signature payloads, and graph semantics during parallel development.

If the deferred neural baseline is built, it adds one fixture, `nco_masks_judge.json`. It is not part of the MVP fixture set. It holds the judge mission's expected step-0 task mask and the expected agent mask for each ready task under each of the three topologies. The masks are computed by `allocation.validate_plan` semantics (the CP-SAT constraint set) rather than by the environment, so the environment can be checked against an independent oracle.
