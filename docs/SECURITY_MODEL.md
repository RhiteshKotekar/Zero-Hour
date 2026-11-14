# Assurance Control Plane (ACP) Security Model

## Security objective

The ACP prevents a false report from contaminating the protected LinUCB learner. It does this by treating reports as untrusted claims, even when a registered agent signed them correctly. The ACP validates identity, authority, freshness, and independent evidence before it can emit a learning-eligible outcome.

This is a simulation assurance mechanism, not a production PKI or safety certification system.

## Threat model

| Threat | Example in SAMG | ACP response |
| --- | --- | --- |
| Unauthorized reporter | Unknown agent claims a mission outcome | Reject key/agent authorization. |
| Forged report | Signature was not created by the registered key | Reject Ed25519 verification. |
| Replay | A previously valid report is resent | Reject used nonce, duplicate report ID, or stale issue time. |
| Cross-mission reuse | Valid report is attached to another mission | Reject mission, agent assignment, or topology-decision mismatch. |
| Signed false claim | Compromised simulated agent signs an inflated reward | Independent evidence contradicts it; reject with `EVIDENCE_MISMATCH`. |
| Missing/weak evidence | Report is authentic but cannot be corroborated | Return `INDETERMINATE`; do not learn. |
| Evidence supplied by reporter | Same agent signs both claim and supposed proof | Not independent; insufficient for a learning-grade decision. |
| *(neural baseline only)* Poisoned allocator training data | Agent claims or episodes are fed into neural allocator training, so a signed false report shapes future allocations | Training accepts only generator instances and `allocation.common.evaluate` rewards (INV-10). There is no code path from persistence to `nco/train.py`. |
| *(neural baseline only)* Checkpoint substitution or tampering | A different or modified `.pt` file is placed where the frozen checkpoint should be, or a pickled payload executes code on load | SHA-256 must match the `FROZEN` registry row and the manifest. Loading uses `weights_only=True` (INV-11). |
| *(neural baseline only)* Mask bug or reward hacking | The policy finds a plan that scores well under the training reward but violates a hard constraint | `allocation.validate_plan` re-checks every plan before simulation. A failure falls back to CP-SAT or greedy with a reason code (INV-12). |
| *(neural baseline only)* Train/test leakage | Allocator trained on instances later used for evaluation | Disjoint `nco-train` / `nco-dev` / `nco-test` seed ranges, also disjoint from the Experiment 1/2 splits (INV-13). |

Out of scope: theft of a registered private key, physical-world sensor integrity, network confidentiality, side channels, a Byzantine majority of evidence sources, denial of service, and, for the deferred neural baseline, adversarial perturbation of allocator inputs and compromise of the training machine or the PyTorch/XPU toolchain. These limits must be displayed with Experiment 2 results so the demo does not overclaim security.

## Identity and signatures

- Use Ed25519 via `cryptography`. Each simulated agent has a generated private key held only in simulation memory/test fixtures and a registered public key identified by `key_id`.
- An identity registry maps `agent_id` and `key_id` to a public key, active status, allowed report types, and authorised task classes. Persist public-key metadata only; do not write private keys to SQLite or logs.
- Sign the exact `AgentReport.signed_payload_bytes()` described in [the data contract](DATA_MODEL.md#ids-times-and-serialization). Verification uses those exact bytes and the public key registered for the claimed agent/key ID.
- Signatures are encoded as URL-safe base64. Invalid base64, unknown algorithms, malformed payloads, and mismatched schema versions are rejected before evidence evaluation.

## Validation state machine

```text
RECEIVED
  -> schema valid?          no -> REJECTED: MALFORMED
  -> key and signature?     no -> REJECTED: AUTHENTICATION_FAILED
  -> agent authorised?      no -> REJECTED: UNAUTHORISED
  -> fresh and unreplayed?  no -> REJECTED: STALE_OR_REPLAYED
  -> mission context match? no -> REJECTED: CONTEXT_MISMATCH
  -> independent evidence?  no -> INDETERMINATE: INSUFFICIENT_EVIDENCE
  -> evidence agrees?       no -> REJECTED: EVIDENCE_MISMATCH
                           yes -> VALID: LEARNING_ELIGIBLE
```

Validation output is terminal and append-only. A later evidence arrival may create a new validation attempt referencing the original report, but it cannot mutate the original decision. Only `VALID` is learning eligible.

## Evidence rules

For the initial simulation, an evidence artifact is independent when its `source_id` is neither the report's `agent_id` nor an alias registered to that identity. `source_id` can be the simulator's trusted event recorder, a designated coordinator record, or a configured independent observer.

Evidence must:

1. reference the same mission and the relevant task/allocation/decision context;
2. have a timestamp within the configured mission/report tolerance;
3. come from a trusted source type configured for that evidence kind;
4. have a matching payload hash and schema;
5. support the claimed completion/metrics/reward within explicit metric tolerances.

Do not compare a self-reported scalar reward alone. ACP derives `validated_reward` from corroborated ground-truth metrics using the active reward schema, then records every evidence ID and tolerance used. This makes acceptance explainable and avoids teaching from a reporter-chosen number.

## Freshness and replay policy

Initial defaults, kept in experiment configuration rather than hard-coded:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `max_report_age_seconds` | 300 | Latest allowed age at validation time. |
| `max_clock_skew_seconds` | 5 | Permitted future timestamp skew. |
| `evidence_tolerance_seconds` | 30 | Maximum report/evidence observation separation. |
| `metric_relative_tolerance` | 0.02 | Default reward/metric agreement tolerance. |

ACP rejects a nonce already recorded for the same agent, a duplicate report ID, an issue time too far in the future, or a report outside its mission execution window. The database unique index on `(agent_id, nonce)` is the durable replay barrier; in-memory caches are only an optimisation.

## Evidence-gated learning boundary

```text
protected path:
  AgentReport -> ACP.validate -> ValidationDecision(VALID)
              -> build LearningEvent(validated_reward) -> policy.observe

vulnerable comparison path:
  AgentReport with valid signature -> extract claimed reward -> vulnerable_policy.observe
```

The comparison path is intentionally unsafe and exists only in experiment code. Its class/module name must include `Vulnerable` and it must never be selected by default application wiring. The protected policy independently checks `validation_status == VALID` before changing `A` or `b`, logs rejected attempts, and raises a domain error if invoked with an ineligible event.

## Offline training plane and model artefacts (deferred neural baseline)

**Not part of the MVP.** The hackathon build has no neural component, and INV-05 applies to it exactly as written. This section applies only if the optional, local-only neural allocator baseline is built later (D022, following [Luttmann & Xie, ICAPS 2024](PAPER_ALIGNMENT.md)). That baseline is trained with RL, and RL training creates a second route by which data can shape future decisions. The rule "only validated rewards may update the learner" is therefore **restated rather than dropped** (D026). INV-10 to INV-13 apply only while the baseline is enabled.

- **INV-05 (restated).** Only `ADMITTED` episodes may update persistent **online** policy state (LinUCB, UCB1). The neural baseline has no online update; it is frozen before any run that uses it.
- **INV-10: training provenance.** Training rewards are a *planning objective*, `−allocation.common.evaluate(...).weighted_total`, computed by trusted code on instances drawn from the seeded generator's `nco-train` range. The paper uses the same pattern: its reward is computed by the deterministic environment, never reported by an agent. Agent claims, witness events and episodes (admitted, provisional or rejected) are never training inputs. `NcoTrainingRun` has no field that could reference them.
- **INV-11: checkpoint integrity.** Weights live at `artifacts/checkpoints/<sha256>.pt`. A load recomputes the SHA-256, requires a matching `FROZEN` row in `model_checkpoints` and a matching manifest entry, and uses `torch.load(path, weights_only=True)`. Checkpoints from outside the repo, the authors' published checkpoints included, are not loaded into recorded runs.
- **INV-12: decode is not trusted.** Feasibility masks make valid plans likely, but they are not a proof. `allocation.validate_plan` (the CP-SAT constraint set plus graph reachability) runs on every neural plan before simulation; CP-SAT and greedy plans may be checked too. A rejected neural plan is replaced by CP-SAT, or by greedy if CP-SAT is unavailable. The record keeps `fallback_used = true` and a `fallback_reason`.
- **INV-13: split disjointness.** The `nco-train`, `nco-dev` and `nco-test` seed ranges are disjoint from each other and from the Experiment 1/2 splits.

The false-report attack (Experiment C) does not target the allocator. With CP-SAT there is nothing to poison, and the neural baseline, if built, is frozen and never reads reports. If online fine-tuning from executed missions is proposed later, it would need its own decision. The proposed rule is "`ADMITTED` episodes and canonical reward only, routed through the same guarded admission API". It would also need its own vulnerable/protected comparison.

## Security tests required before Experiment 2

- valid registered signature + matching independent evidence → `VALID` and exactly one protected update;
- valid registered signature + contradictory evidence → `REJECTED` and zero protected updates;
- invalid signature, unknown key, unauthorised agent, stale timestamp, replayed nonce, and context mismatch → rejected and zero updates;
- insufficient or reporter-owned-only evidence → `INDETERMINATE` and zero updates;
- vulnerable learner demonstrably updates on a validly signed false claim;
- persistence restart retains nonce replay protection and preserves decisions/events.

Additional tests, only if the deferred neural baseline is built (before Experiment E):

- `samg.nco` imports nothing from `samg.persistence`, `samg.assurance` or the report/witness generators. The test is a static import check (INV-10).
- A checkpoint with one flipped byte, or with no `FROZEN` row, is refused before deserialisation (INV-11).
- A hand-built neural plan that violates capability, capacity, precedence or reachability is rejected by `validate_plan` and replaced by the fallback, with the reason code recorded (INV-12).
- The seed-range disjointness check passes for the manifest (INV-13).
- A protected LinUCB update count is unchanged whether CP-SAT or the neural allocator produced the plan. The allocator choice must not bypass the admission gate.
