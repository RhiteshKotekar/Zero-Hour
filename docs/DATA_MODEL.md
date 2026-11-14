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

Use append-only records for reports, evidence, validation decisions, and learning events. Corrections are new records that reference superseded IDs; never overwrite an audit event. `learning_events.applied_at` stays null for ineligible protected events, so the dashboard can distinguish attempted poisoning from accepted learning.

## Contract fixtures

Before feature work begins, add these shared JSON fixtures under `tests/contract/fixtures/`:

1. a two-agent, two-dependent-task reachable mission;
2. the same mission with no permitted cross-agent path;
3. a valid signed report with matching independent evidence;
4. a validly signed but false report with contradictory independent evidence;
5. a stale/replayed report.

All teams use these fixtures. They prevent mismatched enum names, timestamps, signature payloads, and graph semantics during parallel development.
