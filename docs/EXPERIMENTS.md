# Experiment Protocol

The first SAMG release has two demonstrations. Both run entirely against controlled simulation scenarios and produce persisted, seed-replayable records. An optional, post-hackathon, local-only allocator comparison (Experiment E, D029) is described after Experiment 2; it is not part of the hackathon results.

## Common protocol

- Define a scenario suite before comparing policies. Each scenario has fixed agent profiles, task graph, network state, resource pressure, and one `scenario_seed`.
- For each seed, run every compared policy against the same scenario inputs and simulator randomness. Do not give a policy an easier random draw.
- Store policy seed separately from scenario seed. The baseline selectors are deterministic.
- Report a mean, median, standard deviation, and 95% bootstrap confidence interval across seeds. Preserve raw per-run values for the dashboard.
- Do not aggregate infeasible missions as a normal zero-reward result without also reporting infeasibility rate.
- Experiments 1 and 2 (brief Experiments A–C) use **CP-SAT with the deterministic greedy fallback** for every compared policy (brief §7.1, D029), and disclose any fallback use. The neural allocator baseline is never used in them.

Initial scenario families should vary at least task dependency density, capability heterogeneity, resource pressure, communication reliability, and coordinator availability. The configuration rather than source code defines exact ranges.

## Experiment 1 — adaptive coordination

### Question

Does LinUCB selection of a feasible organisational topology outperform fixed hierarchical, functional-cell, and distributed policies as mission context changes?

### Policies

1. `AdaptiveLinUCBPolicy` — chooses among eligible topologies and updates from validated simulated ground truth.
2. `FixedHierarchicalPolicy` — chooses hierarchical when feasible; otherwise records that it is not applicable.
3. `FixedFunctionalCellPolicy` — same rule for functional-cell.
4. `FixedDistributedPolicy` — same rule for distributed.

All policies use the same `TopologyBuilder`, allocator, simulation, reward version, and topology eligibility logic. A baseline must not be allowed to use a topology unavailable to LinUCB.

### Context features (initial schema v1)

Features are normalized to `[0, 1]` and stored in this order:

1. task count;
2. dependency density;
3. mandatory-task ratio;
4. capability coverage slack;
5. capability heterogeneity;
6. aggregate resource pressure;
7. permitted network-link density;
8. mean link latency;
9. mean link reliability;
10. coordinator-eligible agent ratio.

The feature order is part of `feature_schema_version`; change it only by making a new version.

### Metrics and success signal

Primary metric: reward per feasible mission. Secondary metrics: mandatory completion rate, deadline adherence, resource efficiency, coordination cost/latency, communication failure rate, solver runtime, topology distribution, and regret proxy (best known topology reward minus selected topology reward for matched scenarios).

The demo supports the adaptation claim only if adaptive performance exceeds the fixed-policy comparison with uncertainty reported, and the policy selects more than one topology across materially different contexts. If results are mixed, present the evidence rather than claiming superiority.

## Experiment 2 — secure learning

### Question

Does ACP evidence gating prevent signed false reports from poisoning topology selection compared with a vulnerable learner that trusts authenticated claims?

### Setup

Start the protected and vulnerable policies from identical LinUCB state, process the same sequence of scenario contexts, and use the same selected-reporting agent setup. An adversary configuration selects a fraction of reports to be false while still signing them with a valid registered private key. False claims should be biased toward a topology the attacker wants the learner to prefer.

Run at least three corruption levels (for example 0%, 20%, and 40%), but label these as scenario configuration rather than universal threat estimates. Keep reliable independent evidence available in protected runs; a separate missing-evidence configuration should demonstrate safe non-learning (`INDETERMINATE`).

### Comparisons and metrics

| Measure | Protected learner | Vulnerable learner |
| --- | --- | --- |
| Report accepted for update | ACP `VALID` only | Valid signature only |
| Reward used | ACP-derived validated reward | Agent's claimed reward |
| Poison update count | expected 0 for rejected/indeterminate claims | expected >0 when false signed claims arrive |
| Policy quality | ground-truth reward on clean evaluation scenarios | same clean evaluation scenarios |

Report false-report rate, ACP rejection/indeterminate rates and reason codes, number of learning updates, parameter/state divergence, clean-evaluation reward, and chosen-topology distribution. The key result is not merely that ACP rejects a report; it is that protected policy quality remains materially closer to the clean/no-attack reference after the attack sequence.

## Experiment E (optional, later, local-only) — neural allocator baseline vs CP-SAT

**Not part of the hackathon MVP, results tables or demo.** It runs after the hackathon, only on the developer laptop that trains the baseline (Intel Arc XPU for training; CPU for recorded inference). It follows the evaluation protocol of [Luttmann & Xie (ICAPS 2024)](PAPER_ALIGNMENT.md) (Tables 3–5), adapted to SAMG (D029). It never replaces or reruns Experiments 1 and 2 (brief Experiments A–C), which use CP-SAT.

### Question

On SAMG allocation instances, how does a frozen HAM + hierarchical-decoder policy compare with CP-SAT (the exact reference) and the greedy heuristic? The comparison covers solution quality, runtime and feasibility, and checks whether any difference depends on mission size.

### Setup

- **Instances.** Generated by the scenario generator from the `nco-test` seed range, which is disjoint from `nco-train`, `nco-dev` and the Experiment 1/2 splits (INV-13). The run covers all three topologies and the base `h0`/`h1` setting.
- **Size sweep.** The judge mission size (8 tasks, 6 agents) plus larger generator sizes, if adopted (PAPER_ALIGNMENT Q4, deferred). For example, 8/16/32 tasks with proportionally more agents. Report the sample count per size.
- **Solvers.**
  - `NEURAL_HAM` with greedy decoding, with seeded sampling (`W = 10`), and with beam search (width ≤ 100);
  - `CP_SAT` with the configured time limit, plus one longer-limit run that serves as the best-known reference;
  - `GREEDY`.

  Every plan is checked with `allocation.validate_plan`. Neural plans that fail count as failures, even if the fallback rescues the mission.
- **Checkpoint.** The single `FROZEN` checkpoint selected on `nco-dev`, which must pass 100 % of plans through the validator with a mean gap to CP-SAT ≤ 5 %. No tuning on `nco-test`.

### Metrics

- **Quality.** Objective (`allocation.common.evaluate`), and the gap to the best valid plan for the same instance (mean, std, max).
- **Feasibility.** Fraction of instances solved, validator pass rate, fallback rate with reason codes.
- **Runtime.** Per instance, with the device stated: CPU for recorded inference.
- **Training cost.** Wall-clock time, device and parameter count, reported next to the results, as [P] Table 5 does.

### Ablations (only if time allows; the first one is the minimum)

1. Hierarchical decoder vs a flat composite `(task, agent)` decoder [P Table 4].
2. Topology-cost ablation `h0 = h1 = 0` on the neural allocator. Assignments must change relative to the base setting on at least some instances, or the graph is decorative for this allocator (§12.10).
3. HAM vs a homogeneous AM encoder [P Table 3].

### Allocator sensitivity of Experiment 1

Optional, later. If a checkpoint was frozen, Experiment 1's held-out evaluation may be re-run locally with the neural allocator in place of CP-SAT. Report whether the topology ranking and the P3-vs-P1/P2 conclusions still hold. This is a robustness check reported separately; the hackathon results stay the CP-SAT results.

### Claims this experiment may and may not support

- **May:** "the neural allocator reaches X % mean gap to CP-SAT at Y× lower runtime on N instances of size S".
- **May not:** "neural beats CP-SAT", unless measured. At small sizes, [P] itself reports only parity with an exact solver.
- **May not:** any real-world warehouse or robotics claim.

## Run manifest

Each experiment execution writes a manifest containing:

- experiment name and configuration hash;
- git commit/package version where available;
- feature/reward/policy schema versions;
- scenario and policy seeds;
- CP-SAT parameters and fallback use;
- topology eligibility reasons;
- attack/evidence configuration;
- allocator used (`solver`) and whether the greedy fallback ran; for Experiment E runs only, also:
  - checkpoint SHA-256 and `model_checkpoints` row;
  - training run ID, `nco-*` seed ranges and objective version;
  - decode strategy and seed;
  - inference device and torch version;
- timestamp and machine-independent deterministic inputs.

The dashboard must make it possible to select an experiment ID, inspect an individual mission path, and download or display this manifest alongside aggregate charts.
