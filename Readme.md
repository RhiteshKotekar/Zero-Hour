# SAMG — Secure Adaptive Mission Graphs

SAMG is a **controlled Python simulation** for studying adaptive coordination among heterogeneous autonomous agents. It compares organisational topologies, allocates constrained tasks, simulates outcomes, and protects learning from dishonest—but correctly signed—reports.

**Status (`main` at `591d490`).** The end-to-end vertical slice works and is deterministic: mission → topology choice → graph → CP-SAT allocation → simulation → signed witness and agent events → ACP admission → guarded LinUCB update → SQLite. It runs from the terminal (`python -m samg demo`), and 298 tests pass. In progress: Experiments A/B (results not yet measured), the Experiment C harness, and the Streamlit dashboard. Some modules are minimal integration versions. Details are in [DEMO.md](docs/DEMO.md#complete-vs-minimal) and [WORK_QUEUE.md](docs/WORK_QUEUE.md).

## What SAMG demonstrates

1. **Adaptive coordination:** a LinUCB policy selects hierarchical, functional-cell, or distributed coordination graphs and is compared with fixed topology baselines.
2. **Secure learning:** a vulnerable learner trusts signed reports. A protected learner updates only from episodes the Assurance Control Plane (ACP) has `ADMITTED` against independent witness evidence, using the reward the ACP recomputed itself.

Task allocation in the MVP and in all main experiments uses OR-Tools CP-SAT with a deterministic greedy fallback. **Later, optional, local-only, and not part of the hackathon MVP:** a neural allocator baseline following [Luttmann & Xie, ICAPS 2024](docs/PAPER_ALIGNMENT.md), to compare against CP-SAT in an optional Experiment E.

SAMG does not control physical robots, drones, or live operational systems. All agents, reports, evidence, and adversaries are simulated.

## Architecture at a glance

```text
Scenario (MissionSpec + AgentProfiles + permitted links)
                 |
                 v
   eligible topologies = buildable AND allocatable (D030)
                 |
                 v
        topology policy (LinUCB / UCB1 / fixed baseline)
                 |
                 v
      executable coordination graph (NetworkX)
                 |
                 +-----------------> constrained allocator (OR-Tools CP-SAT / greedy fallback)
                 |                                  |
                 v                                  v
             simulator <---------------------- AllocationPlan
                 |
                 +--> signed agent claims + signed witness events
                                      |
                                      v
                 ACP: validate -> corroborate -> admit episode
                                      |
                    +-----------------+------------------+
                    |                                    |
                 persist                           ADMITTED only,
                                                ACP-recomputed reward
                                                         |
                                                         v
                                                    LinUCB update
```

The graph is executable: its permitted links, path latency, reliability, and coordination cost affect allocation feasibility, allocation cost, and simulated mission performance.

## Quick start

Requires Python 3.11 or newer (tested with 3.12). The minimal install below is all the CLI and the tests need.

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install pydantic networkx numpy ortools pyyaml pytest hypothesis cryptography
.venv\Scripts\python -m pip install -e . --no-deps
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m samg demo
```

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pydantic networkx numpy ortools pyyaml pytest hypothesis cryptography
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python -m pytest -q
.venv/bin/python -m samg demo
```

`python -m pip install -e ".[dev]"` also works. It additionally installs the dashboard and plotting dependencies in `pyproject.toml` (Streamlit, Plotly, Matplotlib, SQLAlchemy), which the CLI and tests do not need. `requirements.txt` lists the same set for direct installs.

### Demo

`python -m samg demo` runs four deterministic sections, including a short paired policy comparison:

1. a clean judge-mission run, showing every step;
2. a 30-mission learning stream;
3. a validly signed false-report attack against a protected and a vulnerable learner, plus a replay attempt;
4. fixed/best-fixed, UCB1, LinUCB and contextual epsilon-greedy comparison output. The short sample is illustrative,
   not a held-out experiment result.

`python -m samg run --seed 7 --policy linucb --mode protected` shows one mission in full. [DEMO.md](docs/DEMO.md) lists every command and option, and explains each section. Demo settings (for example `alpha = 0.3`) are not experiment results.

The MVP needs no PyTorch, GPU or NPU. The deferred neural baseline ([D027](docs/DECISIONS.md#d027--compute-and-device-policy-for-the-neural-baseline-2026-11-14-deferred-with-d022)) is trained, and optionally benchmarked, only on one developer's laptop, in a **separate** Intel XPU venv (torch 2.15.0+xpu, `device="xpu"`). It never uses PyTorch Geometric, because `GCNConv` fails on XPU.

## Repository map

```text
config/         YAML parameters: topology costs, allocation, reward, experiment, security policy
src/samg/
  domain/       Shared typed contracts: mission, graph, plan, trace, events, episodes, canonical bytes
  topology/     Coordination graph templates and graph-derived costs
  context/      ctx-v1 context features [1, d, h, r, a]
  allocation/   CP-SAT allocator, deterministic greedy fallback, allocation-aware eligibility (D030)
  simulation/   Judge scenario, seeded generator, execution engine, metrics and reward
  witness/      Independent witness service and simulated agent reports
  assurance/    Identities, signatures, freshness, task-state machine, ACP admission
  learning/     LinUCB, UCB1, fixed baselines, VulnerableLinUCB (Experiment C only), protected gate
  persistence/  Append-only SQLite schema and repositories
  evaluation/   Experiment A/B runner, metrics, landscape analysis, attack configuration
  dashboard/    Streamlit views (in progress; the CLI is the fallback)
  orchestration.py, cli.py, demo.py   the mission loop and the `python -m samg` CLI
  nco/          (later, optional) neural allocator baseline; not created for the MVP
docs/           Plans, decisions, demo, work queue, design docs
tests/          Unit, contract and integration test suites
```

## Start here

- [AI context](docs/AI_CONTEXT.md): a self-contained briefing to paste into an AI assistant so it can explain the project and help you work on it.
- [Demo](docs/DEMO.md): CLI commands, and what each demo section shows.
- [Work queue and results log](docs/WORK_QUEUE.md): what is done, running and next; results R1–R9.
- [Validation log](docs/VALIDATION_LOG.md): the Validator's reproduction checklist.
- [Architecture](docs/ARCHITECTURE.md), [Data model](docs/DATA_MODEL.md), [Security model](docs/SECURITY_MODEL.md), [Experiment protocol](docs/EXPERIMENTS.md): the original design documents. Parts are superseded by D010–D021 and D030–D033 (for example the reward formula, the `VALID/INDETERMINATE` statuses and nonce-based replay). Where they disagree, `DECISIONS.md` and the code win.
- [Paper alignment](docs/PAPER_ALIGNMENT.md) — Luttmann & Xie (ICAPS 2024) mapped onto SAMG: the deferred neural allocator baseline, conflicts with the brief and how they are resolved, compute plan, deferred questions.
- [Three-person plan](docs/THREE_PERSON_PLAN.md) — current ownership, phases, gates, and validator checklist (supersedes the four-developer plan).
- [Four-developer plan](docs/IMPLEMENTATION_PLAN.md): superseded by the three-person plan (D009).
- [Technical decisions](docs/DECISIONS.md) — decisions already made so work does not fork architecturally.

## Working agreements

- Treat `samg.domain`, enum values, config keys and the public interfaces in `docs/THREE_PERSON_PLAN.md` §2 as shared contracts. Change them only with an entry in `docs/DECISIONS.md` and updated fixtures. File ownership is in `CLAUDE.md`.
- Keep the dependency direction one-way: domain → topology/allocation/simulation/assurance/learning → persistence/dashboard orchestration. If the later `nco` package is added, it never imports `persistence` or `assurance`. Avoid cross-importing implementation modules.
- Every stochastic operation takes a passed or stored seed. Experiment comparisons use identical scenario seeds across policies.
- A report signature proves authorship, not truth. Only an `ADMITTED` episode with an ACP-recomputed reward may update a protected policy.
- If the deferred neural baseline is ever enabled, it learns offline from generator instances only. It is never trained on reports or episodes, and it is loaded only from a hash-pinned frozen checkpoint (INV-10 to INV-13, D026).
- The first release is a modular monolith with a local SQLite database. No services, Docker, React, or Node.js are needed.
