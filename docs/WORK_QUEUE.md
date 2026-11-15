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
| 8 | stopped | AG | Neural baseline on XPU (local only): benchmark, train ≤ 90 min, eval vs CP-SAT/greedy. Stopped 2026-11-15 to save usage for the MVP (post-hackathon work, D022). Saved on `nco/baseline` @ `0564673`: MDP, HAM model, XPU-safe ops, checkpoints, benchmark/train/eval scripts; data + device benchmark under `artifacts/nco/` (local). Resume = merge `a/contracts`, regenerate references after D031, train, eval | `docs/NCO_RESULTS.md` with measured table |
| 9 | done | A | Merge item 7 into `a/contracts`; review it (constraints, seeding, gate, ownership); fix issues. Merged into `main` at `591d490` | Full suite green (298 tests); demo reproducible (R9) |
| 10 | done | A | Eligibility = topology builds **and** CP-SAT finds a feasible plan (new reason `ALLOCATION_INFEASIBLE`) — see R5 | `feasible_topologies` + D030; runner uses it (R6) |
| 11 | done | A | Real `MissionExecutor` over orchestration; run Experiments A/B on dev; tune `alpha` on dev only | Dev results table |
| 12 | done | A | Freeze `config/experiment.yaml` (hash), run held-out test; results table + §12.10 falsification checklist | Measured table, claims marked supported/not |
| 13 | done | A | Ablations §12.9 (+ `span_overhead` 0/0.05/0.10/0.20, D031): topology cost = 0; `h0/h1` low/base/high; `link_cost` 0 vs base (D021); two reward-weight sets | Sensitivity table; parameter-sensitivity verdict |
| 14 | queued | A | Simulator hardening if item 7 is minimal: ground-truth oracle record, hop failures, jitter bounds, invalid-plan outcome | Simulator unit tests |
| 15 | done | A+B | Experiment C (S1 vs S2) on the demo's attack path; frozen attack config; FRR with denominators | Security table |
| 16 | done | A | Dashboard views 1–2 (Streamlit, thin over existing functions); CLI stays the fallback | Views render saved runs |
| 17 | done | A+V | Demo bundles (clean + attack), README quick start on a clean venv, `VALIDATION_LOG.md` hand-off | V can reproduce from README |
| 18 | done | A | Push `a/contracts` to `main` | Pushed through `46b6f08`; later team work arrived via PR #2 and direct pushes |
| 19 | later | A | Neural baseline integration: Experiment E (local), decoder ablations, 16/32-task sweep | Only after the MVP ships |
| 20 | done | A+B | Contextual epsilon-greedy P4 comparator; separate dev tuning and multi-policy-seed evaluation | Dev tuned; 60 held-out missions run; results recorded in `docs/RESULTS.md` (R12) |
| 21 | running (AG) | A | Docs consolidation: merge redundant Markdown (IMPLEMENTATION_PLAN → THREE_PERSON_PLAN, VALIDATOR_HANDOFF → VALIDATION_LOG, ASSURANCE_AND_LEARNING_EXPLAINED + SECURITY_MODEL → one doc), renumber the duplicate D038 (twin → D039, control center → D040), bring ARCHITECTURE/DATA_MODEL/EXPERIMENTS/AI_CONTEXT/CLAUDE.md in line with the code | Branch `work/docs-merge`; links resolve; tests unchanged |
| 22 | running (AG, Sonnet) | A | Epsilon-greedy P4 analysis: correctness vs D038, per-decision latency profile and faster variants (cached inverses), accuracy variants tested on dev/design seeds only | `docs/EPSILON_GREEDY_ANALYSIS.md` on `work/eps-analysis` |
| 23 | running (AG) | A | Model v2 (D041, opt-in; default stays v1 so the demo, dashboard and twin are unchanged): comm-loss task failure, real deadlines, relay queueing; re-run A/B (incl. P4) and C from dev tuning | `docs/RESULTS_v2.md`, `docs/RESULTS_SECURITY_v2.md`; demo byte-identical to the v1 reference |
| 24 | queued | A | VAL-001: frozen A/B result differs across environments (Linux/Py 3.14 vs Windows/Py 3.12; P3−P1 −0.0059 vs −0.0013, same config hash). Find the source (OR-Tools/CP-SAT version or platform, numpy, float order), record full environment in every manifest, state reproduction scope in RESULTS | Cause identified; manifests carry environment |
| 25 | queued | A+B | Duplicate code: `samg.twin` re-implements `samg.warehouse` (same module names) — Streamlit/orchestration/engine use `samg.warehouse`, the FastAPI server uses `samg.twin`. Agree on one package, keep the other as a thin re-export or delete | One warehouse package; all UIs green |
| 26 | queued | V | VAL-002: complete the INV-01…INV-09 trace table from the brief's §8.9 wording | Trace table filled |
| 27 | done | A | Model v2 steps 1–2 (opt-in, D041): comm-loss task failure with one retry, real deadlines, relay queueing; design-seed landscape check. Evidence-gate change turned out unnecessary | Rules + 6 tests; demo and twin 3D state byte-identical; landscape verdict (R14) |
| 28 | done | A | Conventional baseline core (`samg.baseline`, D042): greedy travel-aware dispatcher over the WMS controller star, claim-trusting execution, `run_mode(spec, mode, cfg, sim)` (no twin edits), opt-in common random numbers | Brief tests 1–6 + no-SAMG-mechanism guard pass; 407 tests; twin 3D state byte-identical (R15) |
| 29 | done | A | Warehouse scenarios W1–W6, `samg.experiments.run` / `.compare`, results + manifest | `c1be584` |
| 30 | done | A | Comparison ladder (B0 baseline → B1 +CP-SAT → B2 +witness → SAMG, + cold start) on 30 seeds; `RESULTS_BASELINE.md` | RQ1–RQ6 answered (R16) |
| 31 | partly done | A | Side-by-side **replay** page `/compare-replay` (new page; existing 3D views untouched), export script `scripts/export_compare_replays.py`. Remaining: Streamlit comparison tab (step 5); live side-by-side deferred | Page builds, lints, type-checks, serves; real data only |
| 32 | proposed | A+B | SAMG admission control / batching: plan a feasible, priority-first subset when a wave exceeds fleet capacity, defer the rest (today CP-SAT needs every task assigned, so overload = nothing executes). Touches the twin's wave planning → needs user and Dev B sign-off (3D constraint) | W2 overload seeds no longer 0% |
| 33 | proposed | A | Travel-aware allocation objective: add estimated A* travel time to CP-SAT's cost (the baseline's advantage under normal load) | W1 fulfilment gap to B0 closes |

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

### R10 — Experiment C: evidence gate vs signed false reports (D036, D037)
- **Result:** at 20% / 40% corruption the vulnerable learner (S1) admitted 6/6 and 12/12 false signed reward claims, and 27/30 and 26/30 of its follow-up topology choices changed. The protected learner (S2) admitted 0/6 and 0/12, and its matrices are byte-identical to the no-attack reference. Legitimate reports wrongly blocked: 0/537 and 0/534. Replay: 211/211 events rejected with no duplicate updates. Witness withheld: 15/15 episodes PROVISIONAL and no protected updates.
- **Significance:** the security claim holds for learner state and later decisions. It does **not** hold for mission utility: the follow-up reward difference is −0.002 [−0.005, 0.001], because rewards barely differ between topologies. The zero false-rejection rate is expected with a faithful, noise-free witness.
- **Architecture:** none. Full table in `docs/RESULTS_SECURITY.md`.

### R11 — Experiments A/B: adaptive selection vs baselines (D034, D035)
- **Result (60 held-out missions, config hash 8b98c35a16a6d069):** P3 LinUCB 0.7718, P1 best fixed (DISTRIBUTED) 0.7732, P2 UCB1 0.7655. P3 − P1 = −0.0013 [−0.0033, +0.0005]. P3 − P2 = +0.0063 [+0.0038, +0.0090], but only because UCB1 locked onto the worst arm; on the base ablation set it is +0.0002. Across 10 ablation settings, P3 − P1 is never significantly positive.
- **Significance:** high. The adaptive-coordination claim is **not supported**. Every topology completes every mission (C = 1.000), so all reward differences are below 0.01. The graph itself is functional: coordination cost differs between topologies on 60/60 missions.
- **Architecture:** the selection machinery works, but the mission model gives topology too little leverage on reward. To make topology matter, the model would need outcomes that topology can change (deadline misses, task failures from communication loss, capacity pressure), not only small duration and overhead terms. Any such change must be predeclared and re-run from dev tuning. Open question: how to score a fixed policy when its arm is ineligible (currently N/A; P1 was N/A on 6/60 test missions).

### R12 — Contextual epsilon-greedy comparator (D038)
- **Result:** dev tuning chose epsilon 0.05 from `{0.05, 0.1, 0.2, 0.3, 0.5}` using five policy seeds. The full held-out sweep ran all five values on the same 60 missions, each over five policy seeds. Epsilon 0.5 had the highest P4 mean (0.76979); all epsilon values trailed LinUCB and best-fixed, and exceeded this UCB1 run. Detailed paired intervals are in `docs/RESULTS.md`; config hash `e74de5917e5e0dde`.
- **Significance:** higher exploration improved P4's mean across this grid but did not overtake LinUCB or best-fixed. The best-fixed result is based on 54 eligible missions; the UCB1 outcome reflects that run locking onto FUNCTIONAL_CELL. The chosen epsilon remains 0.05 under the dev-only tuning rule. The original frozen P0-P3 config/results remain unchanged.
- **Architecture:** `scripts/run_experiment_epsilon_greedy.py --all-epsilons` reuses the frozen split, baselines, mission seeds, and independent five policy seeds per epsilon; records are saved in `epsilon_sweep_records.csv` and `epsilon_sweep_result.json`. The CLI demo also prints an explicitly illustrative small comparison.

### R13 — Team integration: warehouse twin, control center, epsilon-greedy (pulled 2026-11-15)
- **Result:** `main` gained a warehouse digital twin (`samg.warehouse` with Streamlit tabs, and a `samg.twin` live port), a FastAPI server (`samg.api`) and a Next.js + React Three Fiber control center (`web/`), plus Dev A's contextual epsilon-greedy P4. Merged into `a/contracts` at `c6fdff3`. One test module crashed collection without Streamlit; it now skips (`dec2852`). Full suite: 392 passed with all declared dependencies.
- **Significance:** SAMG now has three judge-facing entry points: the CLI demo, the Streamlit dashboard and the Next.js control center. The warehouse twin feeds congestion and robot breakdowns into the simulator, so physical events change SAMG's timing, reward and witness evidence. P4 trails LinUCB and best-fixed on the held-out set for every epsilon tried (R12), so the adaptive claim is still not supported under model v1.
- **Architecture:** a new layer sits above the unchanged SAMG pipeline: Python twin → FastAPI/WebSocket → browser, with the physical navigation graph and the coordination graph kept separate. Three issues: duplicate D038 numbering (item 21), duplicate warehouse packages (item 25), and cross-environment reproducibility of the frozen A/B result (item 24).

### R14 — Model v2 landscape check (item 27, D041; design seeds, simulated ground truth)
- **Result:** 108 design missions × eligible topologies × 5 simulation seeds. Under v1 no run lost any work (C = 1.000 in 0/1,580 runs below 1). Under v2, 681/1,580 runs completed less than everything (mean C 0.911). The best topology by mean simulated reward moved from DISTRIBUTED 57% / HIERARCHICAL 37% / FUNCTIONAL_CELL 6% (v1) to HIERARCHICAL 53% / DISTRIBUTED 39% / FUNCTIONAL_CELL 8% (v2), and varies within every family. The mean best-to-second gap rose only from 0.0080 to 0.0110 (median 0.0064 → 0.0085).
- **Significance:** v2 makes outcomes depend on coordination. Completion now varies, and the best arm varies by mission without any single arm dominating. But the expected gap between topologies is still about 0.01 reward, while per-run variance rises sharply. That is the regime where a learner needs many missions to separate arms, so a significant LinUCB advantage over best-fixed remains uncertain. This is borderline against the predeclared check (margins "still < 0.01" → report and continue): the mean is 0.011, the median 0.0085.
- **Architecture:** no change outside the simulator. Model v2 is available to the conventional-baseline comparison (W4 communication failure, W6 mixed stress) and to an optional v2 re-run of Experiment A/B. Whether to spend that run is a user decision.

### R15 — Conventional baseline core (item 28, D042)
- **Result:** `samg.baseline` runs the identical twin missions under a greedy centralized dispatcher that trusts authenticated claims. On the judge demo (robot failure + malicious robot), SAMG rejected 2/2 false completion claims, with 0 corrupted tasks and 4/4 orders truly fulfilled. The baseline accepted 2/2, so 1 task was believed done but never happened and 1 of 4 orders shipped incomplete. The twin's existing KPI counted that order as fulfilled for the baseline (completion rate 1.0 in both modes). On the clean preset the baseline was faster (average fulfilment 200 s vs 225 s, utilisation 0.33 vs 0.29), and it planned and ran in about 0.06 s against SAMG's 14.5 s.
- **Significance:** the security difference is measured from genuine mechanisms. Both modes receive the same signed claims; only the verification differs. The baseline also wins on some performance metrics, so the comparison is not one-sided. The twin's order-completion KPI is optimistic whenever claims are trusted, so comparisons must use `orders_truly_fulfilled`.
- **Architecture:** a new `samg.baseline` package composed from twin functions. Opt-in common random numbers were added to the simulator for paired comparisons. No twin, API or web change.

### R16 — SAMG vs conventional baseline, 30 seeds × W1–W6 (items 29–30, D042)
- **Result:** see `RESULTS_BASELINE.md`.
  - The witness/evidence gate is the one large, significant benefit. Under a malicious robot (W5), B0 and B1 accept 2/2 false claims and truly fulfil 71.4% of orders; B2 and SAMG accept 0 and fulfil 100% (+28.6 points), at +11.8 s average fulfilment.
  - Under normal load the greedy, travel-aware baseline is faster than every CP-SAT configuration (W1 +13.6 s) with equal completion.
  - Adaptive topology selection adds almost nothing over a fixed controller star; the exception is +3.2 points under communication failure (W4).
  - Under overload (W2), SAMG executes nothing on 15/30 seeds, because CP-SAT must assign every task of a wave and the fleet capacity is exceeded. The baseline completes all 30.
  - Per-mission wall-clock: 0.06–0.17 s (B0) vs 1.2–5.0 s (SAMG).
- **Significance:** high. This is the first measurement against a competent conventional control. It supports SAMG's security claim, and it refutes performance superiority under normal and overloaded conditions in this model.
- **Architecture:** two proposed changes: admission control / batching in wave planning (item 32) and a travel-aware allocation objective (item 33). Neither is made, because item 32 touches the twin.
