# Conventional baseline vs SAMG — inspection and plan

Status: plan for review; no baseline code exists yet. This answers the eight questions in the baseline brief (2026-11-15) before implementation. Work queue items 27–31.

## 1. Existing modules that can be reused

| Need | Reuse | Notes |
| --- | --- | --- |
| Same warehouse, robots, orders, task set | `samg.twin` (`WarehouseEnv`, `generate_tasks`, `initial_states`, `orders_from_config`, `config/twin.yaml`) | One environment object per run; both modes build it from the same `RunSpec`. |
| Physical execution (A* routes, aisle locks, congestion, travel distance, battery) | `twin.environment.replay_wave`, `twin.path_planning.route/distance` | Identical physics for both modes; collision avoidance stays in both (physical, not coordination). |
| Task execution timing, robot breakdowns, delays | `simulation.engine.run(..., task_delays_ms, agent_breakdowns, agent_down_at_ms, forced_failures)` | The simulator is shared; only the plan fed to it differs. |
| Fault injections | `twin.scenarios.Injection` (`robot_failure`, `comm_failure`, `aisle_blockage`, `delayed_task`, `inventory_unavailable`, `malicious_report`) | Same injection objects resolved against each mode's own plan. |
| False completion attack | `evaluation.attacks.AttackConfig` (abandons a task, signs false completion and reward claims with the robot's real key) | The baseline receives the same signed claims; it just has no witness check. |
| Metrics | `twin.adapter.compute_kpis` via `build_state` (order completion, fulfilment, task latency, utilisation, travel, congestion, task failures, security violations, makespan) | One metric definition for both modes; no new metric code except baseline-specific fields. |
| Communication cost | Engine handoff hops, delay, `hop_failure_probability`, retries; `CoordinationGraph` | Baseline uses a fixed controller star built with the existing hierarchical template. |
| Multi-seed statistics | `evaluation.metrics.summarize`, `paired_comparison` (bootstrap CIs) | Paired by seed. |
| Greedy assignment | `allocation.greedy` ordering logic | Extended with travel distance; not CP-SAT. |

## 2. Where the baseline connects

`twin.adapter.run_wave` is the single point where a wave is planned and executed. Today it always calls `feasible_topologies` → `policy.select` → `run_single_mission` (CP-SAT, witness, ACP, guarded update). The baseline adds a mode switch there:

```text
mode == "samg":     feasible_topologies → policy.select → run_single_mission (unchanged)
mode == "baseline": controller star graph → baseline.dispatch (greedy, travel-aware)
                    → engine.run (same physics) → accept robots' claims (no witness, no ACP)
```

Wave-to-wave state is the key difference. SAMG marks a task done only if the witness verified it (`done |= verified`). The baseline marks it done when the robot **claims** completion. So a false completion is never redone, and its order ships incomplete. That consequence comes from the trust model itself, not from a scripted penalty.

## 3. Current simulation state interface

- Input: `RunSpec(seed, policy, injections, orders, experience, use_cpsat, replan, max_waves, scenario)` plus `config/twin.yaml`.
- Run: `run_warehouse(spec) -> WarehouseRun` (waves, holds, tasks, initial and final robot states, policy state before and after).
- Per wave: `Wave(record = MissionRunRecord, replay = WaveReplay, injections_applied, verified, failing_robots, ...)`.
- Output contract: `build_state(run) -> dict` (the `twin-state` contract in `CONTROL_CENTER_PLAN.md` §4, including `kpis`), served by `samg.api` and rendered by `web/`.

The baseline returns the same `WarehouseRun`/`build_state` shape. `record` becomes a baseline record (`mode="baseline"`, no decision or episode), so every UI and metric path works unchanged.

## 4. Metrics reused

`compute_kpis` already produces: `orders_total`, `orders_dispatched`, `order_completion_rate`, `on_time`, `avg_fulfilment_s`, `avg_task_latency_s`, `robot_utilization`, `travel_m`, `congestion_s`, `congestion_events`, `task_failures`, `unverified_tasks`, `security_violations`, `makespan_s`, `replans`.

Add only what is missing:
- `messages`, `retransmissions`, `comm_delay_s` (from engine handoff records);
- `recovery_s` (robot failure to reassignment);
- `false_claims`, `false_claims_detected`, `false_claims_accepted`;
- `corrupted_tasks`: believed complete but not complete in ground truth;
- `orders_shipped_incomplete`.

The SAMG reward is computed after the run for both modes, as an evaluation score only. The baseline never learns from it.

## 5. Failure and security mechanisms reused

- Robot failure: `Injection("robot_failure")` → engine breakdown. The baseline controller then does greedy reassignment of the unfinished task in the next wave (conventional recovery), with no topology change.
- Communication failure: `Injection("comm_failure")` raises the per-hop loss probability. **This needs model v2 (D041)**: under v1, a lost hop only adds delay and never fails a task, so "communication failure" would show retransmission delay only. Model v2 rule 1 (one retry, then the dependent task fails) is what makes the comm-failure experiment meaningful, and it applies to both modes.
- Malicious agent: `AttackConfig` produces signed false claims. SAMG goes through signature → witness → `DISPUTED` → excluded and replanned. The baseline only checks the signature (conventional authentication) and accepts the claim.

## 6. Files to create

```text
src/samg/baseline/__init__.py
src/samg/baseline/dispatcher.py     greedy travel-aware dispatch → AllocationPlan over a controller star
src/samg/baseline/execution.py      run a wave without topology/LinUCB/witness/ACP; claim-trusting state
src/samg/experiments/__init__.py
src/samg/experiments/scenarios.py   W1 normal, W2 high congestion, W3 robot failure, W4 comm failure,
                                    W5 malicious agent, W6 mixed stress (mapped onto twin injections/orders)
src/samg/experiments/run.py         python -m samg.experiments.run --mode samg|baseline --scenario … --seed …
src/samg/experiments/compare.py     python -m samg.experiments.compare --scenario … --seeds 1..30
config/baseline.yaml                dispatcher weights (declared once, not tuned against SAMG)
tests/unit/baseline/, tests/integration/test_baseline_vs_samg.py
src/samg/dashboard/view_baseline.py Streamlit "SAMG vs conventional baseline" tab
docs/RESULTS_BASELINE.md            measured tables only
```

## 7. Files to modify

- `twin/adapter.py`: mode switch in `run_wave`/`execute`/`run_warehouse`; claim-based vs witness-based `done`.
- `twin/scenarios.py`: `RunSpec.mode`; presets for the W-scenarios.
- `twin/live.py`, `api/app.py`: a `mode` parameter, and a side-by-side session (two sessions with the same `RunSpec` except `mode`).
- `web/`: an execution-mode selector (SAMG / Baseline / Side-by-side) and a capability panel showing actual state.
- `simulation/engine.py`: model v2 rules (opt-in), a prerequisite for W4 and W6.
- `docs/DECISIONS.md` (D042 baseline definition), `docs/WORK_QUEUE.md`, `docs/AI_CONTEXT.md`.

No change to LinUCB, topology templates, witness, ACP or the existing experiments.

## 8. Risks to experimental fairness

1. **Optimiser confound (largest risk).** SAMG plans with CP-SAT and the baseline with greedy. A raw SAMG-vs-baseline gap would mix "better optimiser" with "adaptive topology" and "witness". Mitigation: report a **comparison ladder** on the same seeds:
   - B0 baseline (greedy, fixed star, no witness);
   - B1 + CP-SAT;
   - B2 + witness/ACP (= SAMG with a fixed topology, existing P0-H);
   - SAMG (adaptive).
   Each step isolates one mechanism and answers RQ1, RQ2, RQ5 and RQ6 separately.
2. **Random-number drift.** The engine draws hop losses and jitter in plan order. Two different plans therefore consume the seed differently, and "same seed" is not "same luck". Mitigation: common random numbers keyed by `(seed, task_id, attempt, hop)` so equal events get equal draws in both modes.
3. **Learning head start.** The twin's adaptive policy starts from a trained snapshot (`learning.experience`). Report SAMG both warm and cold, and never let evaluation seeds feed learning.
4. **Security by construction.** "False claims rejected" is 0 for the baseline because it has no witness, which is a capability difference, not a measured win. Report it as such, together with its **consequences**, which are measured: corrupted tasks, orders shipped incomplete, downstream starts. Also report SAMG's cost for the witness: messages, latency, compute (RQ6).
5. **Communication-model asymmetry.** The baseline's controller star costs 2 hops per handoff through the controller, under the same hop delay, loss and retry rules as SAMG. It is never given zero communication cost.
6. **Strawman risk.** Dispatcher weights are declared once in `config/baseline.yaml` before any comparison run, and checked for sanity on design seeds only. The baseline does nearest-robot, priority-aware greedy assignment and greedy reassignment after failure. No random assignment, no artificial delays.
7. **Naming clash.** The brief's "Experiments A–F" collide with the existing Experiments A–E. The warehouse scenarios are named **W1–W6** instead.
8. **Scope and cost.** Side-by-side 3D needs two live sessions and web changes. That is the most expensive piece, so it comes last, after measured results exist.

## Order of work

1. Model v2 rules (opt-in, demo unchanged), with the BLOCKED-as-terminal fix in the evidence gate.
2. Baseline core: dispatcher, claim-trusting execution, `RunSpec.mode`, common random numbers, tests 1–7 from the brief.
3. W1–W6 scenarios, single-seed run CLI, multi-seed compare CLI, results JSON/CSV with manifest (seed, config, scenario, mode, git commit, environment).
4. Comparison ladder run on 10 seeds, then 30; `RESULTS_BASELINE.md`.
5. Streamlit comparison tab.
6. Web mode selector and side-by-side view.
