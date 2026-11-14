# Experiment Protocol

The first SAMG release has two demonstrations. Both run entirely against controlled simulation scenarios and produce persisted, seed-replayable records.

## Common protocol

- Define a scenario suite before comparing policies. Each scenario has fixed agent profiles, task graph, network state, resource pressure, and one `scenario_seed`.
- For each seed, run every compared policy against the same scenario inputs and simulator randomness. Do not give a policy an easier random draw.
- Store policy seed separately from scenario seed. The baseline selectors are deterministic.
- Report a mean, median, standard deviation, and 95% bootstrap confidence interval across seeds. Preserve raw per-run values for the dashboard.
- Do not aggregate infeasible missions as a normal zero-reward result without also reporting infeasibility rate.

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

## Run manifest

Each experiment execution writes a manifest containing:

- experiment name and configuration hash;
- git commit/package version where available;
- feature/reward/policy schema versions;
- scenario and policy seeds;
- CP-SAT parameters and fallback use;
- topology eligibility reasons;
- attack/evidence configuration;
- timestamp and machine-independent deterministic inputs.

The dashboard must make it possible to select an experiment ID, inspect an individual mission path, and download or display this manifest alongside aggregate charts.
