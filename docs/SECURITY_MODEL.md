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

Out of scope: theft of a registered private key, physical-world sensor integrity, network confidentiality, side channels, a Byzantine majority of evidence sources, and denial of service. These limits must be displayed with Experiment 2 results so the demo does not overclaim security.

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

## Security tests required before Experiment 2

- valid registered signature + matching independent evidence → `VALID` and exactly one protected update;
- valid registered signature + contradictory evidence → `REJECTED` and zero protected updates;
- invalid signature, unknown key, unauthorised agent, stale timestamp, replayed nonce, and context mismatch → rejected and zero updates;
- insufficient or reporter-owned-only evidence → `INDETERMINATE` and zero updates;
- vulnerable learner demonstrably updates on a validly signed false claim;
- persistence restart retains nonce replay protection and preserves decisions/events.
