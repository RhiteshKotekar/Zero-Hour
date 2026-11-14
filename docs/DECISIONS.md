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

## D004 — Separate signed claims from validated outcomes

**Decision:** `AgentReport` is never a learner input. ACP produces `ValidationDecision`; only `VALID` decisions can yield a protected `LearningEvent`.

**Why:** Digital signatures authenticate origin but cannot prove report truth. The separation makes Experiment 2 meaningful and testable.

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
