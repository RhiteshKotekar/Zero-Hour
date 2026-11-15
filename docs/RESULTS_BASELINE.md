# SAMG vs conventional baseline — measured results (W1–W6)

Generated 2026-11-15T09:10:43+00:00 from commit `49b8b9fe`; seeds 1001–1030 (n = 30); mission model v2 with common random numbers for every rung (D041, D042). Values are means with 95% bootstrap intervals across seeds. Paired differences are per seed. Nothing was tuned on these seeds.

Ladder: **B0** = Conventional baseline (greedy central dispatch, claims trusted); **B1** = + CP-SAT optimiser (SAMG's optimiser, claims still trusted); **B2** = + witness & evidence gate (SAMG pipeline with a fixed controller star (no adaptation)); **SAMG** = SAMG (adaptive) (+ LinUCB topology selection (warm start)); **SAMG-cold** = SAMG (adaptive, cold start) (LinUCB with no pre-training)


**Provenance.** The run started from the experiment code later committed as `c1be584`. The manifest recorded the commit at the end of the run (`49b8b9f`, after a merge). `git diff c1be584 49b8b9f -- src config scripts` is empty, so the rows reproduce at either commit. Future runs record the commit at start.

## Findings (30 seeds per scenario; paired per seed; * = 95% CI excludes 0)

| Question | Answer from the data |
| --- | --- |
| RQ5: does the witness/evidence gate stop false completion claims? | **Yes.** W5: B0/B1 accept 2/2 false claims per run, with 1 task believed done but not done and 28.6 points fewer orders truly fulfilled (71.4% vs 100%). B2 and SAMG accept 0. Step B2−B1: +0.286* truly fulfilled. |
| RQ6: what does that protection cost? | W5 step B2−B1: +11.8 s* average fulfilment and +41.7 s* makespan, because SAMG re-plans the abandoned work. Wall-clock per mission run: B0 0.06–0.17 s vs SAMG 1.2–5.0 s (CP-SAT, signing, witness, ACP). |
| RQ1: does SAMG beat conventional dispatch on performance? | **No, not under normal load.** W1: same completion (100%), but SAMG is 13.6 s* slower on average fulfilment. The greedy dispatcher scores robots by A* travel distance; SAMG's CP-SAT allocator does not model travel (B1−B0 = +13.4 s*). Same pattern in W3 (+29.2 s*) and W5. |
| RQ2: does adaptive topology selection help? | **Barely.** SAMG−B2 (adaptive vs fixed controller star): no truly-fulfilled difference in W1, W2, W3, W5. W4 communication failure: +3.2 points (CI touches 0 vs B2; +3.2* vs B0). It is slower in W3 (+4.8 s*) and W5 (+1.9 s*). Warm vs cold start makes little difference. |
| RQ3: robot failure | W3: every configuration fulfils 100%; B0 recovers fastest (284 s vs 313 s for SAMG). |
| RQ4: communication failure | W4: SAMG 100% truly fulfilled vs 96.8% for B0/B1/B2 (+3.2* vs B0), at +26 s* average fulfilment. |
| Overload (W2, W6) | **SAMG fails outright when a wave has more tasks than the fleet can take.** In 15/30 W2 seeds (for example 46 tasks against a per-wave capacity of 40), CP-SAT finds no plan under any topology, so nothing executes: 0% fulfilled. The greedy baseline assigns what fits, defers the rest to the next wave and fulfils 100% in all 30 seeds. W6 (overload + faults): B0 70.3% vs SAMG 47.2% truly fulfilled; on the seeds where SAMG can plan, it wins on integrity (0 corrupted tasks vs 1.3). |

**What this changes in the architecture.**
1. The evidence gate is SAMG's measured benefit: it is the only mechanism with a large, significant effect, and only under attack.
2. Adaptive topology selection adds little under the current mission model.
3. SAMG needs **admission control / batching**: plan a feasible subset of tasks (priority-first) and defer the rest, instead of requiring every task to be assigned. Without it, overload means total failure.
4. SAMG's allocator should include **travel time** (the baseline's advantage under normal load).

Items 3 and 4 touch the twin's wave planning and the allocation objective. They are proposed changes (`WORK_QUEUE.md` items 32–33), not done.

## W1 — Normal warehouse

Seeded order book, no faults.

| Metric | B0 | B1 | B2 | SAMG | SAMG-cold |
|---|---:|---:|---:|---:|---:|
| truly_fulfilled_rate | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| order_completion_rate | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| orders_shipped_incomplete | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| corrupted_tasks | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| false_claims_accepted | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| avg_fulfilment_s | 213.1 [203.9, 222.5] | 226.6 [218.6, 234.2] | 226.7 [218.6, 234.3] | 226.7 [218.6, 234.3] | 226.7 [218.6, 234.3] |
| avg_task_latency_s | 15.6 [12.9, 18.3] | 18.8 [17.0, 20.5] | 18.8 [17.0, 20.6] | 18.8 [17.0, 20.6] | 18.8 [17.0, 20.6] |
| makespan_s | 255.0 [237.7, 273.6] | 268.5 [256.5, 279.5] | 268.6 [256.6, 279.6] | 268.8 [256.6, 279.9] | 268.8 [256.6, 279.9] |
| robot_utilization | 27.6% [26.0%, 29.0%] | 26.2% [23.9%, 28.4%] | 26.2% [23.9%, 28.5%] | 26.2% [23.9%, 28.5%] | 26.2% [23.9%, 28.5%] |
| travel_m | 362.1 [323.5, 400.0] | 364.1 [325.4, 402.5] | 364.1 [325.4, 402.5] | 364.1 [325.4, 402.5] | 364.1 [325.4, 402.5] |
| congestion_s | 27.0 [19.7, 35.6] | 25.9 [18.6, 33.5] | 26.6 [18.8, 34.8] | 26.6 [18.8, 34.8] | 26.6 [18.8, 34.8] |
| task_failures | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| retransmissions | 1.200 [0.667, 1.800] | 1.067 [0.600, 1.567] | 1.067 [0.600, 1.567] | 1.067 [0.600, 1.567] | 1.067 [0.600, 1.567] |
| runtime_s | 0.073 [0.063, 0.083] | 0.693 [0.342, 1.123] | 1.389 [0.799, 2.147] | 2.333 [0.863, 4.522] | 1.478 [0.798, 2.378] |

| Paired step (per seed, first minus second) | Metric | Mean diff | 95% CI | Seeds higher/lower/tie |
|---|---|---:|---|---|
| B1-B0 (optimiser) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B1-B0 (optimiser) | avg_fulfilment_s | +13.4233 | [+5.8973, +20.7783] | 21/9/0 |
| B1-B0 (optimiser) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B1-B0 (optimiser) | runtime_s | +0.6202 | [+0.2741, +1.0464] | 30/0/0 |
| B2-B1 (witness & evidence gate) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B2-B1 (witness & evidence gate) | avg_fulfilment_s | +0.0996 | [+0.0000, +0.2989] | 1/0/29 |
| B2-B1 (witness & evidence gate) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B2-B1 (witness & evidence gate) | runtime_s | +0.6963 | [+0.4153, +1.0794] | 30/0/0 |
| SAMG-B2 (adaptive topology) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B2 (adaptive topology) | avg_fulfilment_s | +0.0284 | [+0.0000, +0.0852] | 1/0/29 |
| SAMG-B2 (adaptive topology) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B2 (adaptive topology) | runtime_s | +0.9436 | [-0.0219, +2.7688] | 19/11/0 |
| SAMG-B0 (SAMG overall) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B0 (SAMG overall) | avg_fulfilment_s | +13.5514 | [+5.9650, +20.9084] | 21/9/0 |
| SAMG-B0 (SAMG overall) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B0 (SAMG overall) | runtime_s | +2.2601 | [+0.7917, +4.4470] | 30/0/0 |
| SAMG-cold-SAMG (cold vs warm start) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | avg_fulfilment_s | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | runtime_s | -0.8549 | [-2.6925, +0.1066] | 12/18/0 |

## W2 — High congestion

Larger order book (6-9 orders) for more concurrent tasks and aisle conflicts.

| Metric | B0 | B1 | B2 | SAMG | SAMG-cold |
|---|---:|---:|---:|---:|---:|
| truly_fulfilled_rate | 100.0% [100.0%, 100.0%] | 50.0% [33.3%, 70.0%] | 50.0% [33.3%, 70.0%] | 50.0% [33.3%, 70.0%] | 50.0% [33.3%, 70.0%] |
| order_completion_rate | 100.0% [100.0%, 100.0%] | 50.0% [33.3%, 70.0%] | 50.0% [33.3%, 70.0%] | 50.0% [33.3%, 70.0%] | 50.0% [33.3%, 70.0%] |
| orders_shipped_incomplete | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| corrupted_tasks | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| false_claims_accepted | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| avg_fulfilment_s | 301.8 [286.1, 316.9] | 284.8 [271.8, 299.9] | 282.2 [270.3, 296.0] | 283.9 [272.5, 296.1] | 285.1 [273.7, 297.2] |
| avg_task_latency_s | 30.7 [29.4, 32.1] | 35.8 [32.6, 39.2] | 35.3 [32.3, 38.6] | 35.8 [32.8, 38.8] | 35.9 [32.9, 38.9] |
| makespan_s | 474.7 [436.8, 508.4] | 182.5 [118.6, 251.2] | 182.0 [117.9, 251.0] | 182.3 [118.5, 250.8] | 182.0 [118.3, 250.5] |
| robot_utilization | 33.3% [31.8%, 34.9%] | 39.5% [37.7%, 41.1%] | 39.3% [37.4%, 40.9%] | 39.4% [37.7%, 40.8%] | 39.4% [37.7%, 40.8%] |
| travel_m | 819.8 [775.1, 863.5] | 368.0 [238.9, 507.0] | 368.3 [239.0, 507.2] | 366.6 [238.2, 504.9] | 366.6 [238.2, 504.8] |
| congestion_s | 42.5 [32.3, 52.3] | 29.0 [16.5, 43.8] | 27.7 [16.8, 40.6] | 28.0 [16.1, 42.0] | 28.1 [16.2, 42.1] |
| task_failures | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| retransmissions | 3.100 [2.433, 3.800] | 1.367 [0.767, 2.133] | 1.367 [0.767, 2.133] | 1.367 [0.767, 2.133] | 1.367 [0.767, 2.133] |
| runtime_s | 0.171 [0.147, 0.194] | 2.645 [1.815, 3.529] | 4.841 [3.289, 6.539] | 4.781 [3.238, 6.466] | 4.762 [3.205, 6.467] |

| Paired step (per seed, first minus second) | Metric | Mean diff | 95% CI | Seeds higher/lower/tie |
|---|---|---:|---|---|
| B1-B0 (optimiser) | truly_fulfilled_rate | -0.5000 | [-0.6667, -0.3000] | 0/15/15 |
| B1-B0 (optimiser) | avg_fulfilment_s | +7.9360 | [-2.5493, +18.3765] | 11/4/0 |
| B1-B0 (optimiser) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B1-B0 (optimiser) | runtime_s | +2.4746 | [+1.6338, +3.3739] | 25/5/0 |
| B2-B1 (witness & evidence gate) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B2-B1 (witness & evidence gate) | avg_fulfilment_s | -2.6305 | [-8.0421, +0.7479] | 2/2/11 |
| B2-B1 (witness & evidence gate) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B2-B1 (witness & evidence gate) | runtime_s | +2.1954 | [+1.4352, +3.0341] | 30/0/0 |
| SAMG-B2 (adaptive topology) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B2 (adaptive topology) | avg_fulfilment_s | +1.6965 | [-6.8060, +10.0449] | 3/1/11 |
| SAMG-B2 (adaptive topology) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B2 (adaptive topology) | runtime_s | -0.0593 | [-0.1839, +0.0164] | 14/16/0 |
| SAMG-B0 (SAMG overall) | truly_fulfilled_rate | -0.5000 | [-0.6667, -0.3000] | 0/15/15 |
| SAMG-B0 (SAMG overall) | avg_fulfilment_s | +7.0021 | [-7.6193, +19.2742] | 11/4/0 |
| SAMG-B0 (SAMG overall) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B0 (SAMG overall) | runtime_s | +4.6108 | [+3.0593, +6.3069] | 29/1/0 |
| SAMG-cold-SAMG (cold vs warm start) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | avg_fulfilment_s | +1.2735 | [+0.0000, +3.8206] | 1/0/14 |
| SAMG-cold-SAMG (cold vs warm start) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | runtime_s | -0.0193 | [-0.1056, +0.0399] | 16/14/0 |

## W3 — Robot failure

A transport robot breaks down during its first transport task.

| Metric | B0 | B1 | B2 | SAMG | SAMG-cold |
|---|---:|---:|---:|---:|---:|
| truly_fulfilled_rate | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| order_completion_rate | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| orders_shipped_incomplete | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| corrupted_tasks | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| false_claims_accepted | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| avg_fulfilment_s | 284.0 [267.6, 301.4] | 308.4 [291.5, 324.6] | 308.4 [291.5, 324.6] | 313.1 [296.0, 330.3] | 312.5 [295.7, 329.1] |
| avg_task_latency_s | 23.2 [21.0, 25.4] | 27.9 [25.1, 30.4] | 27.9 [25.1, 30.4] | 27.9 [25.1, 30.4] | 27.8 [25.0, 30.3] |
| makespan_s | 359.6 [335.8, 382.0] | 381.8 [361.6, 399.0] | 381.8 [361.6, 399.0] | 389.3 [369.1, 407.2] | 388.6 [368.6, 405.8] |
| robot_utilization | 19.8% [18.5%, 20.9%] | 18.8% [17.3%, 20.3%] | 18.8% [17.3%, 20.3%] | 18.5% [17.0%, 19.9%] | 18.5% [17.0%, 19.9%] |
| travel_m | 371.5 [333.0, 409.4] | 374.9 [337.6, 411.9] | 374.9 [337.6, 411.9] | 371.5 [333.8, 409.3] | 372.0 [334.0, 409.9] |
| congestion_s | 24.7 [18.8, 31.3] | 26.5 [18.7, 34.7] | 26.5 [18.7, 34.7] | 26.5 [18.7, 34.7] | 26.3 [18.6, 34.2] |
| task_failures | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| retransmissions | 1.400 [0.967, 1.867] | 1.200 [0.800, 1.667] | 1.200 [0.800, 1.667] | 1.000 [0.633, 1.400] | 1.000 [0.633, 1.400] |
| runtime_s | 0.072 [0.064, 0.079] | 0.661 [0.328, 1.081] | 1.246 [0.764, 1.880] | 1.253 [0.761, 1.907] | 1.289 [0.768, 1.988] |

| Paired step (per seed, first minus second) | Metric | Mean diff | 95% CI | Seeds higher/lower/tie |
|---|---|---:|---|---|
| B1-B0 (optimiser) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B1-B0 (optimiser) | avg_fulfilment_s | +24.4024 | [+5.9094, +43.0665] | 20/10/0 |
| B1-B0 (optimiser) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B1-B0 (optimiser) | runtime_s | +0.5897 | [+0.2596, +1.0098] | 30/0/0 |
| B2-B1 (witness & evidence gate) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B2-B1 (witness & evidence gate) | avg_fulfilment_s | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B2-B1 (witness & evidence gate) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B2-B1 (witness & evidence gate) | runtime_s | +0.5845 | [+0.3976, +0.8289] | 30/0/0 |
| SAMG-B2 (adaptive topology) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B2 (adaptive topology) | avg_fulfilment_s | +4.7860 | [+3.4726, +6.1947] | 29/1/0 |
| SAMG-B2 (adaptive topology) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B2 (adaptive topology) | runtime_s | +0.0071 | [-0.0304, +0.0491] | 16/14/0 |
| SAMG-B0 (SAMG overall) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B0 (SAMG overall) | avg_fulfilment_s | +29.1885 | [+10.2529, +47.7612] | 22/8/0 |
| SAMG-B0 (SAMG overall) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B0 (SAMG overall) | runtime_s | +1.1813 | [+0.6933, +1.8383] | 30/0/0 |
| SAMG-cold-SAMG (cold vs warm start) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | avg_fulfilment_s | -0.6183 | [-1.8549, +0.0000] | 0/1/29 |
| SAMG-cold-SAMG (cold vs warm start) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | runtime_s | +0.0358 | [-0.0068, +0.0896] | 13/17/0 |

## W4 — Communication failure

Per-hop message loss raised to the twin's comm-failure level.

| Metric | B0 | B1 | B2 | SAMG | SAMG-cold |
|---|---:|---:|---:|---:|---:|
| truly_fulfilled_rate | 96.8% [93.8%, 99.3%] | 96.8% [92.2%, 100.0%] | 96.8% [92.2%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| order_completion_rate | 96.8% [93.8%, 99.3%] | 96.8% [92.2%, 100.0%] | 96.8% [92.2%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| orders_shipped_incomplete | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| corrupted_tasks | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| false_claims_accepted | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| avg_fulfilment_s | 287.2 [267.9, 306.6] | 309.2 [289.9, 328.0] | 309.2 [289.9, 328.0] | 313.1 [295.0, 330.7] | 314.6 [296.5, 332.4] |
| avg_task_latency_s | 14.2 [11.4, 17.0] | 16.6 [14.5, 18.4] | 16.6 [14.5, 18.4] | 16.7 [14.7, 18.7] | 16.7 [14.8, 18.5] |
| makespan_s | 356.6 [329.5, 383.3] | 375.9 [350.6, 400.2] | 375.9 [350.6, 400.2] | 377.0 [354.3, 399.1] | 380.8 [358.5, 402.8] |
| robot_utilization | 19.9% [18.6%, 21.4%] | 18.9% [17.4%, 20.4%] | 18.9% [17.4%, 20.4%] | 18.9% [17.4%, 20.3%] | 18.7% [17.3%, 20.1%] |
| travel_m | 364.7 [326.1, 401.9] | 370.4 [331.5, 409.6] | 370.4 [331.5, 409.6] | 365.5 [326.9, 403.9] | 367.8 [329.5, 405.8] |
| congestion_s | 26.5 [20.1, 33.2] | 26.0 [18.7, 33.8] | 26.0 [18.7, 33.8] | 26.1 [18.7, 33.8] | 25.7 [18.6, 33.2] |
| task_failures | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| retransmissions | 15.2 [13.6, 16.7] | 13.8 [12.0, 15.4] | 13.8 [12.0, 15.4] | 11.9 [10.3, 13.4] | 11.9 [10.3, 13.4] |
| runtime_s | 0.061 [0.056, 0.065] | 0.606 [0.279, 1.031] | 1.172 [0.672, 1.825] | 1.151 [0.646, 1.804] | 1.188 [0.671, 1.860] |

| Paired step (per seed, first minus second) | Metric | Mean diff | 95% CI | Seeds higher/lower/tie |
|---|---|---:|---|---|
| B1-B0 (optimiser) | truly_fulfilled_rate | +0.0000 | [-0.0500, +0.0333] | 2/1/27 |
| B1-B0 (optimiser) | avg_fulfilment_s | +22.0022 | [-0.2008, +41.6702] | 22/8/0 |
| B1-B0 (optimiser) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B1-B0 (optimiser) | runtime_s | +0.5448 | [+0.2201, +0.9648] | 30/0/0 |
| B2-B1 (witness & evidence gate) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B2-B1 (witness & evidence gate) | avg_fulfilment_s | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B2-B1 (witness & evidence gate) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B2-B1 (witness & evidence gate) | runtime_s | +0.5667 | [+0.3704, +0.8178] | 30/0/0 |
| SAMG-B2 (adaptive topology) | truly_fulfilled_rate | +0.0317 | [+0.0000, +0.0783] | 3/0/27 |
| SAMG-B2 (adaptive topology) | avg_fulfilment_s | +3.9888 | [-0.7333, +8.5293] | 20/8/2 |
| SAMG-B2 (adaptive topology) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B2 (adaptive topology) | runtime_s | -0.0216 | [-0.0421, -0.0035] | 10/20/0 |
| SAMG-B0 (SAMG overall) | truly_fulfilled_rate | +0.0317 | [+0.0067, +0.0617] | 4/0/26 |
| SAMG-B0 (SAMG overall) | avg_fulfilment_s | +25.9910 | [+4.1788, +44.9894] | 23/7/0 |
| SAMG-B0 (SAMG overall) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B0 (SAMG overall) | runtime_s | +1.0900 | [+0.5859, +1.7412] | 30/0/0 |
| SAMG-cold-SAMG (cold vs warm start) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | avg_fulfilment_s | +1.4769 | [+0.3611, +2.8416] | 6/0/24 |
| SAMG-cold-SAMG (cold vs warm start) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | runtime_s | +0.0375 | [+0.0011, +0.0926] | 17/13/0 |

## W5 — Malicious agent

A picking robot abandons a task and signs false completion and reward claims.

| Metric | B0 | B1 | B2 | SAMG | SAMG-cold |
|---|---:|---:|---:|---:|---:|
| truly_fulfilled_rate | 71.4% [68.1%, 74.2%] | 71.4% [68.1%, 74.2%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| order_completion_rate | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| orders_shipped_incomplete | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| corrupted_tasks | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| false_claims_accepted | 2.000 [2.000, 2.000] | 2.000 [2.000, 2.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| avg_fulfilment_s | 243.6 [235.7, 251.3] | 264.8 [255.6, 274.5] | 276.6 [267.3, 286.3] | 278.5 [268.2, 289.2] | 283.2 [273.0, 293.5] |
| avg_task_latency_s | 13.9 [11.3, 16.4] | 17.4 [15.8, 19.0] | 29.3 [27.4, 31.1] | 29.4 [27.4, 31.3] | 29.4 [27.5, 31.3] |
| makespan_s | 338.8 [325.2, 351.8] | 363.6 [350.3, 376.5] | 405.2 [391.1, 419.3] | 407.8 [393.7, 422.2] | 423.9 [409.2, 438.5] |
| robot_utilization | 20.7% [19.1%, 22.3%] | 19.1% [17.4%, 20.8%] | 18.4% [16.9%, 19.9%] | 18.3% [16.8%, 19.8%] | 18.0% [16.5%, 19.5%] |
| travel_m | 365.0 [326.1, 403.1] | 360.1 [321.4, 398.8] | 389.0 [350.3, 428.2] | 387.6 [349.1, 427.0] | 391.9 [353.0, 432.1] |
| congestion_s | 26.9 [19.8, 34.6] | 26.1 [18.5, 34.1] | 26.1 [18.5, 34.1] | 26.1 [18.5, 34.1] | 25.9 [18.5, 33.7] |
| task_failures | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| retransmissions | 1.300 [0.933, 1.667] | 1.267 [0.867, 1.667] | 1.267 [0.867, 1.667] | 1.267 [0.867, 1.667] | 1.300 [0.933, 1.667] |
| runtime_s | 0.062 [0.054, 0.071] | 0.607 [0.285, 1.020] | 1.204 [0.705, 1.853] | 1.206 [0.696, 1.873] | 1.254 [0.695, 2.039] |

| Paired step (per seed, first minus second) | Metric | Mean diff | 95% CI | Seeds higher/lower/tie |
|---|---|---:|---|---|
| B1-B0 (optimiser) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B1-B0 (optimiser) | avg_fulfilment_s | +21.2437 | [+14.0902, +28.0402] | 24/6/0 |
| B1-B0 (optimiser) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| B1-B0 (optimiser) | runtime_s | +0.5446 | [+0.2238, +0.9570] | 30/0/0 |
| B2-B1 (witness & evidence gate) | truly_fulfilled_rate | +0.2861 | [+0.2578, +0.3189] | 30/0/0 |
| B2-B1 (witness & evidence gate) | avg_fulfilment_s | +11.8280 | [+10.2276, +13.6101] | 30/0/0 |
| B2-B1 (witness & evidence gate) | corrupted_tasks | -1.0000 | [-1.0000, -1.0000] | 0/30/0 |
| B2-B1 (witness & evidence gate) | runtime_s | +0.5973 | [+0.3859, +0.8533] | 30/0/0 |
| SAMG-B2 (adaptive topology) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B2 (adaptive topology) | avg_fulfilment_s | +1.9026 | [+0.3294, +4.0583] | 10/0/20 |
| SAMG-B2 (adaptive topology) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B2 (adaptive topology) | runtime_s | +0.0017 | [-0.0377, +0.0380] | 16/14/0 |
| SAMG-B0 (SAMG overall) | truly_fulfilled_rate | +0.2861 | [+0.2578, +0.3189] | 30/0/0 |
| SAMG-B0 (SAMG overall) | avg_fulfilment_s | +34.9742 | [+26.7378, +43.0737] | 27/3/0 |
| SAMG-B0 (SAMG overall) | corrupted_tasks | -1.0000 | [-1.0000, -1.0000] | 0/30/0 |
| SAMG-B0 (SAMG overall) | runtime_s | +1.1436 | [+0.6334, +1.8077] | 30/0/0 |
| SAMG-cold-SAMG (cold vs warm start) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | avg_fulfilment_s | +4.6198 | [+2.6924, +6.4044] | 20/1/9 |
| SAMG-cold-SAMG (cold vs warm start) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | runtime_s | +0.0477 | [-0.0455, +0.1862] | 12/18/0 |

## W6 — Mixed stress

High workload plus robot failure, communication failure and a malicious report.

| Metric | B0 | B1 | B2 | SAMG | SAMG-cold |
|---|---:|---:|---:|---:|---:|
| truly_fulfilled_rate | 70.3% [65.1%, 75.1%] | 39.0% [25.3%, 53.6%] | 45.9% [29.9%, 63.0%] | 47.2% [30.9%, 65.0%] | 47.2% [30.9%, 65.0%] |
| order_completion_rate | 86.4% [82.4%, 90.3%] | 45.9% [29.9%, 63.0%] | 45.9% [29.9%, 63.0%] | 47.2% [30.9%, 65.0%] | 47.2% [30.9%, 65.0%] |
| orders_shipped_incomplete | 1.233 [1.000, 1.500] | 0.500 [0.333, 0.700] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| corrupted_tasks | 1.333 [1.133, 1.567] | 0.500 [0.333, 0.700] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| false_claims_accepted | 2.333 [2.133, 2.567] | 1.000 [0.667, 1.400] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| avg_fulfilment_s | 424.3 [408.0, 439.4] | 417.5 [395.3, 441.4] | 423.1 [401.3, 446.2] | 434.6 [412.4, 460.7] | 440.0 [416.7, 466.4] |
| avg_task_latency_s | 34.2 [32.0, 36.3] | 34.2 [30.9, 37.6] | 40.6 [37.2, 44.1] | 42.2 [39.1, 45.3] | 43.1 [39.9, 46.6] |
| makespan_s | 542.0 [524.1, 558.6] | 275.0 [179.0, 377.5] | 280.5 [182.4, 385.2] | 296.5 [194.0, 408.7] | 307.2 [200.1, 422.9] |
| robot_utilization | 27.7% [26.3%, 29.1%] | 25.5% [24.3%, 26.8%] | 25.9% [24.8%, 27.0%] | 24.8% [23.7%, 26.0%] | 24.1% [23.0%, 25.3%] |
| travel_m | 802.9 [758.3, 843.6] | 359.8 [232.9, 496.1] | 375.3 [244.2, 516.3] | 378.1 [244.8, 520.8] | 381.1 [246.2, 524.8] |
| congestion_s | 44.3 [35.4, 53.6] | 29.4 [17.3, 43.8] | 29.4 [17.3, 43.8] | 27.7 [17.2, 39.0] | 27.7 [17.2, 39.0] |
| task_failures | 1.333 [1.133, 1.533] | 0.733 [0.433, 1.033] | 0.733 [0.433, 1.033] | 0.767 [0.467, 1.067] | 0.767 [0.467, 1.067] |
| retransmissions | 32.0 [29.6, 34.5] | 13.8 [9.000, 19.3] | 14.1 [9.133, 19.8] | 12.8 [8.267, 17.9] | 12.8 [8.300, 17.9] |
| runtime_s | 0.164 [0.143, 0.186] | 2.657 [1.798, 3.576] | 4.941 [3.314, 6.734] | 5.028 [3.381, 6.860] | 4.994 [3.351, 6.828] |

| Paired step (per seed, first minus second) | Metric | Mean diff | 95% CI | Seeds higher/lower/tie |
|---|---|---:|---|---|
| B1-B0 (optimiser) | truly_fulfilled_rate | -0.3136 | [-0.4491, -0.1614] | 6/17/7 |
| B1-B0 (optimiser) | avg_fulfilment_s | -3.9956 | [-23.7170, +16.2250] | 6/9/0 |
| B1-B0 (optimiser) | corrupted_tasks | -0.8333 | [-1.1000, -0.6000] | 0/20/10 |
| B1-B0 (optimiser) | runtime_s | +2.4929 | [+1.6362, +3.4246] | 25/5/0 |
| B2-B1 (witness & evidence gate) | truly_fulfilled_rate | +0.0688 | [+0.0448, +0.0950] | 15/0/15 |
| B2-B1 (witness & evidence gate) | avg_fulfilment_s | +5.6023 | [-1.9054, +13.3068] | 9/6/0 |
| B2-B1 (witness & evidence gate) | corrupted_tasks | -0.5000 | [-0.7000, -0.3333] | 0/15/15 |
| B2-B1 (witness & evidence gate) | runtime_s | +2.2839 | [+1.4361, +3.2249] | 30/0/0 |
| SAMG-B2 (adaptive topology) | truly_fulfilled_rate | +0.0131 | [+0.0000, +0.0292] | 3/0/27 |
| SAMG-B2 (adaptive topology) | avg_fulfilment_s | +11.5644 | [-4.8581, +25.6660] | 12/3/0 |
| SAMG-B2 (adaptive topology) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-B2 (adaptive topology) | runtime_s | +0.0876 | [-0.0238, +0.2389] | 15/15/0 |
| SAMG-B0 (SAMG overall) | truly_fulfilled_rate | -0.2316 | [-0.3931, -0.0518] | 13/15/2 |
| SAMG-B0 (SAMG overall) | avg_fulfilment_s | +13.1711 | [-9.2196, +36.6601] | 9/6/0 |
| SAMG-B0 (SAMG overall) | corrupted_tasks | -1.3333 | [-1.5667, -1.1333] | 0/30/0 |
| SAMG-B0 (SAMG overall) | runtime_s | +4.8643 | [+3.2152, +6.7103] | 25/5/0 |
| SAMG-cold-SAMG (cold vs warm start) | truly_fulfilled_rate | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | avg_fulfilment_s | +5.3243 | [+2.5756, +8.9189] | 13/1/1 |
| SAMG-cold-SAMG (cold vs warm start) | corrupted_tasks | +0.0000 | [+0.0000, +0.0000] | 0/0/30 |
| SAMG-cold-SAMG (cold vs warm start) | runtime_s | -0.0346 | [-0.0796, +0.0005] | 14/16/0 |

## Notes

- `truly_fulfilled_rate` counts an order only if every one of its tasks really happened (ground truth). `order_completion_rate` is the twin's KPI and over-counts for rungs that trust claims (B0, B1).
- Security rows (`false_claims_accepted`, `corrupted_tasks`) are 0 for B2/SAMG by construction of the evidence gate, and the baseline has no witness; read them as the measured consequence of that capability difference.
- `runtime_s` is wall-clock per mission run on the recorded machine (see manifest), not a simulated time.
- Environment: Python 3.12.10, numpy 2.5.4, OR-Tools 9.15.6755, Windows-11-10.0.26200-SP0.
