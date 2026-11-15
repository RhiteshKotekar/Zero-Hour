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
| 7 | done | AG | Integration + barebones demo: simulator, witness, ACP admission, orchestration, `python -m samg demo` | Demo runs deterministically; vertical-slice test green (R9) |
| 8 | paused | AG | Neural baseline on XPU (local only): benchmark, train ≤ 90 min, eval vs CP-SAT/greedy. Paused on a usage limit; data generation finished (26,797 training instances, 26,444 CP-SAT-feasible); training/eval not done | `docs/NCO_RESULTS.md` with measured table |
| 9 | done | A | Merge item 7 into `a/contracts`; review it (constraints, seeding, gate, ownership); fix issues. Merged into `main` at `591d490` | Full suite green (298 tests); demo reproducible (R9) |
| 10 | done | A | Eligibility = topology builds **and** CP-SAT finds a feasible plan (new reason `ALLOCATION_INFEASIBLE`) — see R5 | `feasible_topologies` + D030; runner uses it (R6) |
| 11 | running (AG) | A | Real `MissionExecutor` over orchestration; run Experiments A/B on dev; tune `alpha` on dev only | Dev results table |
| 12 | running (AG) | A | Freeze `config/experiment.yaml` (hash), run held-out test; results table + §12.10 falsification checklist | Measured table, claims marked supported/not |
| 13 | running (AG) | A | Ablations §12.9 (+ `span_overhead` 0/0.05/0.10/0.20, D031): topology cost = 0; `h0/h1` low/base/high; `link_cost` 0 vs base (D021); two reward-weight sets | Sensitivity table; parameter-sensitivity verdict |
| 14 | queued | A | Simulator hardening if item 7 is minimal: ground-truth oracle record, hop failures, jitter bounds, invalid-plan outcome | Simulator unit tests |
| 15 | running (AG) | A+B | Experiment C (S1 vs S2) on the demo's attack path; frozen attack config; FRR with denominators | Security table |
| 16 | running (AG) | A | Dashboard views 1–2 (Streamlit, thin over existing functions); CLI stays the fallback | Views render saved runs |
| 17 | running (AG) | A+V | Demo bundles (clean + attack), README quick start on a clean venv, `VALIDATION_LOG.md` hand-off | V can reproduce from README |
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

### R6 — Allocation-aware eligibility (item 10, D030)
- **Result:** new `samg.allocation.feasible_topologies` runs the allocator before an arm is offered. Generated scenario 16 is the regression case: DISTRIBUTED passes the old pairwise check, but CP-SAT proves no plan exists.
- **Significance:** a policy can no longer pick an arm that is guaranteed to fail. Policies are compared only on arms that can actually be executed, and infeasibility is reported per topology rather than counted against whichever policy chose it.
- **Architecture:** the eligibility contract moves from "structurally buildable" to "buildable and allocatable". Orchestration (Dev B or the demo agent) should call `feasible_topologies` and reuse the returned plan; `eligible_topologies` stays for structural checks. The Experiment A/B runner already uses the new function.

### R7 — Topology landscape before learning (design seeds)
- **Result:** with the cost model at that point, DISTRIBUTED was the best planned topology on ~90% of missions, with a mean margin of only ~0.013 reward. The h0/h1 settings flipped 5–8 of 216 missions; removing the D021 link cost flipped 2.
- **Significance:** high. Experiment A would have shown no adaptive advantage, since P1 = "always distributed" is nearly optimal. The D021 link cost alone was too weak to create a trade-off.
- **Architecture:** led to D031. Design analyses now use seeds ≥ 50 000 (`landscape.DESIGN_SEED_OFFSET`), which never overlap experiment seeds.

### R8 — Span-of-control cost (D031)
- **Result:** with `span_overhead = 0.10` (predeclared), the best-topology shares become DISTRIBUTED 56%, HIERARCHICAL 28%, FUNCTIONAL_CELL 16%. The winners vary within families as well. Sweep: 0 → 91/6/4 (D/H/F), 0.05 → 80/10/10, 0.20 → 35/41/24.
- **Significance:** contextual selection now has something to learn. Margins stay small (~0.008 reward), so the Experiment A effect sizes will be modest and must be reported with confidence intervals and this sensitivity.
- **Architecture:** task duration now depends on (task, agent, topology). This changes the allocator (per-agent intervals in CP-SAT), plan evaluation and the simulator, which must take its durations from the plan.

### R9 — Vertical slice merged (items 7 and 9)
- **Result:** `integration/demo` is merged into `main` at `591d490`. It adds the simulator, witness service, agent reports, ACP admission, orchestration (`execute_mission`, `run_single_mission`) and the CLI (`python -m samg demo`, `python -m samg run`). The full suite passes: 298 tests on Python 3.12, including `tests/integration/test_vertical_slice.py`. Two consecutive `python -m samg demo` runs give byte-identical output. Demo settings, not experiment results: on the judge mission (seed 7) the episode is ADMITTED, and the ACP-recomputed reward (0.7814) equals the simulator ground truth. In the attack section the ACP corroborates 0 of 10 signed false claims and blocks 0 of 177 honest claims; S2 picks the attacker's preferred FUNCTIONAL_CELL 0/10 times. S1 (`VulnerableLinUCB`) learns the claimed reward 10/10 times, picks FUNCTIONAL_CELL 7/10 times, and diverges from S2. Replayed events come back DUPLICATE and the re-offered episode is refused with DUPLICATE_EPISODE.
- **Significance:** high. Gate G2 is reached: one mission goes through the whole loop (features → D030 eligibility → policy → graph → CP-SAT → simulation → witness + signed claims → ACP → guarded update → SQLite). The protected and vulnerable learners demonstrably diverge under a validly signed false report. The run is still a demo: `alpha = 0.3` and the 30-mission stream are not tuned or held out, and the attack harness is not the full Experiment C (item 15).
- **Architecture:** the integrator proposed two conventions that still need ratification. D032 covers the evidence path: the witness signs `VERIFIED_COMPLETE`, the simulated clock and event-id format, the validation order, corroboration and reward-claim rules, and separate SQLite worlds for S1/S2. D033 covers the reward normalisation edge cases; Dev A must confirm it. The engine takes nominal task durations from the plan (`assignment.end - assignment.start`), so D031 span-of-control overhead reaches ground truth. `execute_mission` is policy-free and is the intended basis for the `MissionExecutor` adapter (item 11). The simulator, witness, ACP admission, attack and orchestration modules are marked *integration versions*, and their owners may replace them (see `DEMO.md`, "Complete vs minimal").
