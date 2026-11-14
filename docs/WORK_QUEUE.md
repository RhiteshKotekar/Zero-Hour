# Work queue and results log

The queue is worked in order, top to bottom. Each finished item that produces a result or changes the architecture gets an entry in the results log: what happened, why it matters, and whether the architecture changes. Owner tags: **A** = Dev A (Claude-assisted), **B** = Dev B, **V** = Validator, **AG** = background agent.

## Queue

| # | Status | Owner | Task | Exit criterion |
| --- | --- | --- | --- | --- |
| 1 | done | A | Dev A Phase 0–1: domain contracts, topology, features, generator, CP-SAT + greedy | 274 tests green |
| 2 | done | A | Integrate Dev B PR #1 (enums, fixtures, field names) | Dev B fixture tests run and pass (R1) |
| 3 | done | AG | Paper alignment docs; neural allocator = deferred local-only baseline | D022–D029 on `a/contracts` (R3) |
| 4 | done | A | Experiment A/B runner + metrics (executor injected) | Protocol tests with synthetic oracle |
| 5 | done | AG | Hierarchical-decoder study | Report + change requests sent to neural agent (R4) |
| 6 | done | A | Generator feasible by construction | 633/643 scenario×topology pairs feasible (R5) |
| 7 | running | AG | Integration + barebones demo: simulator, witness, ACP admission, orchestration, `python -m samg demo` | Demo runs deterministically; vertical-slice test green |
| 8 | running | AG | Neural baseline on XPU (local only): benchmark, train ≤ 90 min, eval vs CP-SAT/greedy | `docs/NCO_RESULTS.md` with measured table |
| 9 | next | A | Merge item 7 into `a/contracts`; review it (constraints, seeding, gate, ownership); fix issues | Full suite green; demo reproducible |
| 10 | queued | A | Eligibility = topology builds **and** CP-SAT finds a feasible plan (new reason `ALLOCATION_INFEASIBLE`) — see R5 | Infeasible arms never offered to a policy |
| 11 | queued | A | Real `MissionExecutor` over orchestration; run Experiments A/B on dev; tune `alpha` on dev only | Dev results table |
| 12 | queued | A | Freeze `config/experiment.yaml` (hash), run held-out test; results table + §12.10 falsification checklist | Measured table, claims marked supported/not |
| 13 | queued | A | Ablations §12.9: topology cost = 0; `h0/h1` low/base/high; `link_cost` 0 vs base (D021); two reward-weight sets | Sensitivity table; parameter-sensitivity verdict |
| 14 | queued | A | Simulator hardening if item 7 is minimal: ground-truth oracle record, hop failures, jitter bounds, invalid-plan outcome | Simulator unit tests |
| 15 | queued | A+B | Experiment C (S1 vs S2) on the demo's attack path; frozen attack config; FRR with denominators | Security table |
| 16 | queued | A | Dashboard views 1–2 (Streamlit, thin over existing functions); CLI stays the fallback | Views render saved runs |
| 17 | queued | A+V | Demo bundles (clean + attack), README quick start on a clean venv, `VALIDATION_LOG.md` hand-off | V can reproduce from README |
| 18 | ask | A | Push `a/contracts`, open PR to `main` | User approval |
| 19 | later | A | Neural baseline integration: Experiment E (local), decoder ablations, 16/32-task sweep | Only after the MVP ships |

## Results log

### R1 — Dev B integration (item 2)
- **Result:** Dev B merged first, with UPPERCASE enum values and fixture field names (`capacity`, `duration_ms`, `deadline_ms`, `priority_weight`, `permitted_links`). Dev A's models were aligned to them. Dev B's skipped mission-fixture test now runs and passes.
- **Significance:** the two halves of the system now share one contract, and the signed fixtures did not have to be regenerated.
- **Architecture:** small change. `Scenario.permitted_links`, the physical/policy network, now limits every topology. Functional-cell falls back to a coordinator hub when there is no mission lead. Builders take a `Scenario` (D020).

### R2 — Per-link maintenance cost (D021, proposed)
- **Result:** with hop cost alone, distributed always wins when it is eligible, and functional-cell can never beat hierarchical on the judge mission.
- **Significance:** without a trade-off, the bandit has nothing context-dependent to learn, and Experiment A would be trivial.
- **Architecture:** the coordination overhead `H` gains `link_cost × number of links`. The same rule applies to every topology. It must appear in the sensitivity check (item 13), and the team must ratify it.

### R3 — Paper alignment (item 3)
- **Result:** Luttmann & Xie (ICAPS 2024) applies only to the allocation step.
- **Significance:** none for the hackathon MVP (user decision).
- **Architecture:** none now. After the hackathon, an optional `samg.nco` allocator will sit behind `allocate()` as a local-only comparison baseline. CP-SAT stays the reference, and Experiments A–C use CP-SAT (D022–D029).

### R4 — Hierarchical decoder study (item 5)
- **Result:** keep the task → agent decoder. At SAMG's size it barely shrinks each decision (2.0 feasible task options of 4.6 per step, 1.85 agent options of 6.0; the agent choice is forced 53% of the time). At 32 tasks × 14 agents it gives 46 choices against 448 for a flat decoder. Its agent stage is the natural place to feed in hop distance and handoff cost.
- **Significance:** at the current mission sizes the neural baseline is expected to match CP-SAT at best. Any advantage needs a 16/32-task sweep.
- **Architecture:** no MVP change. Experiment E (later) needs a mission-size sweep and decoder ablations (flat, hybrid).

### R5 — Generator infeasibility fix (item 6)
- **Result:** CP-SAT proved most generated missions infeasible: 100/646 pairs feasible, and about 3% under constrained resources. Budgets and capacities were split without regard to which agents could perform which tasks. They are now sized from a seeded reference assignment, giving 633/643 feasible. All 10 remaining failures are DISTRIBUTED, where the degree cap removes a needed path.
- **Significance:** high. Experiments A–C and any neural training on the old generator would have measured mostly infeasible missions. The bug was found by the decoder study, not by our tests. The sweep test only checked plan validity when a plan was feasible, and now also checks the feasibility rate.
- **Architecture:** a contract-level guarantee is added: every generated mission is feasible under hierarchical coordination (brief §3.4). The remaining distributed failures expose a gap. Topology eligibility checks only pairwise reachability, so a policy can still be offered an arm that allocation will reject. Item 10 proposes adding an allocator feasibility check to eligibility, so an arm is offered only if a feasible plan exists. That changes the `eligible_topologies` contract, which Dev B's orchestration uses, and needs a DECISIONS entry.
