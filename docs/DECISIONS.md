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
