# SAMG — Secure Adaptive Mission Graphs

SAMG is a **controlled Python simulation** for studying adaptive coordination among heterogeneous autonomous agents. It compares organisational topologies, allocates constrained tasks, simulates outcomes, and protects learning from dishonest—but correctly signed—reports.

This repository is intentionally in its **architecture and foundation phase**. The package layout, contracts, experiment protocol, and team ownership are in place; the application components themselves are not yet implemented.

## What SAMG demonstrates

1. **Adaptive coordination:** a LinUCB policy selects hierarchical, functional-cell, or distributed coordination graphs and is compared with fixed topology baselines.
2. **Secure learning:** a vulnerable learner trusts signed reports; a protected learner updates only after Assurance Control Plane (ACP) evidence validation.

SAMG does not control physical robots, drones, or live operational systems. All agents, reports, evidence, and adversaries are simulated.

## Architecture at a glance

```text
MissionSpec + AgentProfiles + NetworkState
                 |
                 v
        topology policy (LinUCB / fixed baseline)
                 |
                 v
      executable coordination graph (NetworkX)
                 |
                 +-----------------> constrained allocator (OR-Tools / greedy fallback)
                 |                                  |
                 v                                  v
             simulator <---------------------- AllocationPlan
                 |
                 +--> signed AgentReport + independent evidence
                                      |
                                      v
                              ACP validation decision
                                      |
                    +-----------------+------------------+
                    |                                    |
                 persist                             valid only
                                                         |
                                                         v
                                                    LinUCB update
```

The graph is executable: its permitted links, path latency, reliability, and coordination cost affect allocation feasibility, allocation cost, and simulated mission performance.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
```

`requirements.txt` is provided for environments that install dependencies directly. The legacy `requirement.txt` delegates to it.

## Repository map

```text
src/samg/
  domain/       Shared typed mission, agent, report, and outcome contracts
  topology/     Coordination graph construction and graph-derived costs
  allocation/   CP-SAT allocator and deterministic greedy fallback
  learning/     LinUCB policy and evidence-gated update boundary
  simulation/   Scenario generation, mission execution, rewards, adversaries
  assurance/    Identities, signatures, freshness, evidence validation
  persistence/  SQLite repositories and immutable event records
  dashboard/    Streamlit experiment viewer
docs/           Architecture, data model, security, experiments, team plan
tests/          Unit, contract, and integration test suites
```

## Start here

- [Architecture](docs/ARCHITECTURE.md) — boundaries, interfaces, and non-negotiable invariants.
- [Data model](docs/DATA_MODEL.md) — shared contracts and SQLite records.
- [Security model](docs/SECURITY_MODEL.md) — ACP validation and learning gate.
- [Experiment protocol](docs/EXPERIMENTS.md) — reproducible demonstrations and metrics.
- [Four-developer plan](docs/IMPLEMENTATION_PLAN.md) — ownership, sequence, and integration rules.
- [Technical decisions](docs/DECISIONS.md) — decisions already made so work does not fork architecturally.

## Working agreements

- Treat `docs/DATA_MODEL.md` and the public interfaces in `docs/ARCHITECTURE.md` as shared contracts. Change them with an entry in `docs/DECISIONS.md`.
- Keep the dependency direction one-way: domain → topology/allocation/simulation/assurance/learning → persistence/dashboard orchestration. Avoid cross-importing implementation modules.
- Every stochastic operation takes a passed or stored seed. Experiment comparisons use identical scenario seeds across policies.
- A report signature proves authorship, not truth. Only an ACP `VALID` decision may cause a learning update.
- The first release is a modular monolith with a local SQLite database. No services, Docker, React, or Node.js are needed.
