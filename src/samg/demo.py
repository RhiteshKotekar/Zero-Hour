"""Judge-facing terminal demo for the Phase 2 vertical slice (owner: Dev B, CLI support).

Minimal integration version, written by the integrator. It only *displays*
what ``samg.orchestration`` does; there is no business logic here. Output is
deterministic for fixed seeds (no wall-clock values are printed).

Sections (``python -m samg demo``):

1. Clean run of the judge mission, every step of the loop.
2. Learning over a stream of generated missions (protected LinUCB), with an
   evaluation-only counterfactual showing which topology was actually best.
3. Signed false-report attack: one pre-attack LinUCB state cloned into a
   protected learner (S2) and ``VulnerableLinUCB`` (S1), identical scenarios and
   attack schedule, side by side; replay attempt; parameter divergence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from samg.allocation import feasible_topologies
from samg.domain import (
    AgentEvent,
    EpisodeStatus,
    EventStatus,
    EventType,
    PolicyMode,
    Scenario,
    TaskState,
    TopologyName,
    WitnessEvent,
)
from samg.evaluation.attacks import AttackConfig
from samg.learning import ARM_ORDER, LinUCBPolicy, TopologyPolicy, VulnerableLinUCB
from samg.orchestration import MissionRunRecord, RunSettings, World, replay_events, run_single_mission
from samg.simulation import compute_reward
from samg.simulation import run as simulate
from samg.simulation.scenarios import factor_grid, generate_scenario, judge_scenario

Out = Callable[[str], None]
MIN = 60_000.0
SHORT = {TopologyName.HIERARCHICAL: "HIER", TopologyName.FUNCTIONAL_CELL: "FUNC", TopologyName.DISTRIBUTED: "DIST"}
RULE = "=" * 100
SUB = "-" * 100


@dataclass(frozen=True)
class DemoConfig:
    """Demo parameters. ``alpha`` is a demo setting, not a frozen experiment value."""

    judge_seed: int = 7
    policy_seed: int = 0
    alpha: float = 0.3
    n_learn: int = 30
    n_attack: int = 10
    stream_seed_base: int = 5000
    compromised_agent: str = "A4"
    preferred_topology: TopologyName = TopologyName.FUNCTIONAL_CELL
    inflation: float = 0.20
    deflation: float = 0.30
    use_cpsat: bool = True
    comparison_train: int = 18
    comparison_test: int = 10


# --- formatting helpers ------------------------------------------------------


def _m(ms: float | None) -> str:
    return "  -  " if ms is None else f"{ms / MIN:6.1f}"


def _vec(v: Sequence[float]) -> str:
    return "[" + ", ".join(f"{x:.3f}" for x in v) + "]"


def _short_id(event_id: str) -> str:
    """``M-.../e0/A4/3`` -> ``A4#3`` for compact tables."""
    parts = event_id.split("/")
    return f"{parts[-2]}#{parts[-1]}"


def _theta(policy: LinUCBPolicy, arm: TopologyName) -> np.ndarray:
    return policy.theta(arm)


# --- section 1: one mission in full ------------------------------------------


def render_mission(record: MissionRunRecord, scenario: Scenario, settings: RunSettings,
                   before: dict[str, Any] | None, policy: TopologyPolicy, out: Out) -> None:
    """Every step of one mission run, from mission intake to the guarded policy update."""
    mission = scenario.mission
    out(f"Mission {mission.mission_id}  scenario={scenario.scenario_id}  seed={record.seed}  epoch={mission.epoch}")
    out(f"Policy  {record.policy_kind}  mode={record.mode.value}  instance={record.policy_instance}")
    out(f"Deadline {mission.deadline_ms / MIN:.1f} min, {len(mission.tasks)} tasks, {len(scenario.agents)} agents")
    out("")
    out("Agents (id, role, capabilities, capacity, budget, flags)")
    for a in scenario.agents:
        flags = ",".join(f for f, on in (("lead", a.is_mission_lead), ("coordinator", a.can_coordinate),
                                         ("UNAVAILABLE", not a.available)) if on)
        out(f"  {a.agent_id:<4} {a.role:<12} {'/'.join(a.capabilities):<38} cap={a.capacity}  "
            f"budget={a.resource_budget:5.1f}  {flags}")
    out("Tasks (id, required capabilities, nominal duration, demand, priority, depends on)")
    for t in mission.tasks:
        sep = " | " if t.capability_match.value == "ANY" else " & "
        out(f"  {t.task_id:<4} {sep.join(t.required_capabilities):<32} {t.duration_ms / MIN:5.1f} min  "
            f"demand={t.resource_demand:3.1f}  prio={t.priority_weight:3.1f}  deps={','.join(t.dependencies) or '-'}")
    out("")

    out("[1] Context features (ctx-v1)")
    out("    " + "  ".join(f"{k}={v:.3f}" for k, v in record.context.as_dict().items()))
    out("[2] Topology eligibility")
    for topo in TopologyName:
        v = record.eligibility[topo]
        why = "eligible" if v.eligible else "INELIGIBLE: " + ",".join(r.value for r in v.reasons) + (
            f" ({v.detail})" if v.detail else "")
        out(f"    {topo.value:<16} {why}")
    d = record.decision
    out(f"[3] Policy scores ({d.policy_kind}; score = mean + bonus)")
    for arm in ARM_ORDER:
        if arm in d.scores:
            mark = "  <== chosen" if arm is d.topology else ""
            mean = d.means.get(arm, 0.0)
            bonus = d.bonuses.get(arm, 0.0)
            out(f"    {arm.value:<16} mean={mean:7.4f}  bonus={bonus:7.4f}  score={d.scores[arm]:7.4f}{mark}")
    how = "cold-start warm-up (seeded arm order)" if d.warmup else "argmax score"
    out(f"    chosen: {d.topology.value if d.topology else 'NONE'}  ({how})")
    if record.graph is None or record.plan is None:
        out("    no eligible topology: mission not run")
        return

    g, plan = record.graph, record.plan
    links = g.coordination_links()
    out(f"[4] Coordination graph {g.topology.value}  version={g.graph_version[:12]}  "
        f"coordinators={','.join(g.coordinators) or '-'}")
    out(f"    {len(links)} links: " + " ".join(f"{a}-{b}" for a, b in links))
    out(f"[5] Allocation  solver={plan.solver.value} status={plan.solver_status} feasible={plan.feasible}"
        + (f"  fallback_used={plan.fallback_used}" if plan.fallback_used else ""))
    if not plan.feasible:
        out("    infeasible: " + ",".join(r.value for r in plan.reason_codes) + f" ({plan.detail})")
    outcomes = {o.task_id: o for o in record.trace.outcomes} if record.trace else {}
    if plan.assignments:
        out("    task  agent   planned start-end (min)   actual start-end (min)   outcome")
    for a in plan.assignments:
        o = outcomes.get(a.task_id)
        status = "-" if o is None else ("completed" if o.completed else f"NOT DONE ({o.failure_reason})")
        out(f"    {a.task_id:<5} {a.agent_id:<6} {_m(a.start)} - {_m(a.end)}           "
            f"{_m(o.start if o else None)} - {_m(o.end if o else None)}          {status}")
    if plan.objective:
        ob = plan.objective
        out(f"    objective: makespan={ob.makespan:.1f} min  handoff_cost={ob.handoff_cost:.2f}  "
            f"max_agent_load={ob.max_agent_load:.1f} min  weighted_total={ob.weighted_total:.2f}")
    if not plan.feasible:
        _render_episode(record, before, policy, out)
        return
    cross = [h for h in plan.handoffs if h.hops > 0]
    out(f"[6] Handoffs (graph-derived: cost = h0 + h1*hops = {settings.costs.h0} + {settings.costs.h1}*hops; "
        f"{settings.costs.handoff_delay_ms_per_hop / MIN:.0f} min/hop)")
    for h in plan.handoffs:
        if h.hops == 0:
            continue
        out(f"    {h.prerequisite_task}->{h.dependent_task}  {h.from_agent}->{h.to_agent}  path={'>'.join(h.path)}  "
            f"hops={h.hops}  cost={h.cost:.2f}  delay={h.delay / MIN:.0f} min")
    same = len(plan.handoffs) - len(cross)
    out(f"    ({same} dependency edge(s) stay on the same agent: cost 0)")
    if record.trace is None:
        _render_episode(record, before, policy, out)
        return

    tr = record.trace
    out(f"[7] Simulated execution (seed {tr.seed}): {len(tr.transitions)} task transitions, "
        f"makespan {tr.metrics.makespan / MIN:.1f} min, message retransmissions {tr.metrics.communication_failures}")
    _render_events(record, out)
    _render_episode(record, before, policy, out)


def _render_events(record: MissionRunRecord, out: Out) -> None:
    w = record.witness_events
    out(f"[8] Evidence: {len(w)} witness events signed by {w[0].witness_id if w else '-'} "
        f"(key {w[0].key_id if w else '-'}); {len(record.agent_events)} signed agent claims")
    auth = Counter(d.status.value for d in record.auth_decisions)
    final = Counter(d.status.value for d in record.final_decisions)
    out("    validate_event: " + ", ".join(f"{k} {v}" for k, v in sorted(auth.items())))
    out("    after corroboration: " + ", ".join(f"{k} {v}" for k, v in sorted(final.items())))
    by_id = {d.event_id: d for d in record.final_decisions}
    auth_by_id = {d.event_id: d for d in record.auth_decisions}
    out("    agent claim   type                 task  auth            evidence decision  reasons")
    for e in record.agent_events:
        f, a = by_id[e.event_id], auth_by_id[e.event_id]
        extra = ""
        if e.event_type is EventType.REWARD_CLAIM:
            extra = f"  claimed_reward={e.payload['claimed_reward']:.4f}"
        out(f"    {_short_id(e.event_id):<12}  {e.event_type.value:<20} {e.task_id or '-':<5} {a.status.value:<15} "
            f"{f.status.value:<17} {','.join(r.value for r in f.reason_codes)}{extra}")


def _render_episode(record: MissionRunRecord, before: dict[str, Any] | None,
                    policy: TopologyPolicy, out: Out) -> None:
    ep = record.episode
    if ep is None:
        return
    out(f"[9] Episode {ep.status.value}  reasons={','.join(r.value for r in ep.reason_codes)}")
    rb, m = record.acp_reward, record.acp_metrics
    if rb is not None and m is not None:
        out("    Reward recomputed by the ACP from witness-verified outcomes (brief 7.2):")
        out("    term          raw metric                 normalised  term value  weight  contribution")
        rows = [
            ("completion", "C", f"weighted completion {m.weighted_completion:.3f}", m.weighted_completion),
            ("duration", "T", f"makespan {m.makespan / MIN:.1f} min", m.duration_norm),
            ("resources", "R", f"resource used {m.resource_used:.1f}", m.resource_norm),
            ("coordination", "H", f"coordination cost {m.coordination_cost:.2f}", m.coordination_norm),
        ]
        for key, sym, raw, norm in rows:
            entering = "C" if sym == "C" else f"1-{sym}"
            out(f"    {key:<13} {raw:<26} {sym}={norm:6.3f}   {entering}={rb.components[key]:6.3f}  "
                f"{rb.weights[key]:5.2f}   {rb.contributions[key]:7.4f}")
        out(f"    reward r = {rb.reward:.4f}")
    gt = record.ground_truth_reward
    if gt is not None and gt.failure_outcome:
        out(f"    plan invalid: predefined failure outcome {gt.failure_label}, reward {gt.reward:.4f} "
            f"(reported, never learned)")
    if record.ground_truth_reward is not None and record.trace is not None:
        out(f"    (evaluation oracle: simulator ground-truth reward {record.ground_truth_reward.reward:.4f})")
    if record.claimed_reward is not None:
        out(f"    last authenticated REWARD_CLAIM: {record.claimed_reward:.4f} "
            f"({'used: VULNERABLE mode' if record.mode is PolicyMode.VULNERABLE else 'recorded for audit, never used'})")
    le = record.learning_event
    out("[10] Guarded policy update")
    if le is None:
        out(f"    no learning event ({record.learning_rejection.value if record.learning_rejection else '-'})")
    elif record.learning_applied:
        out(f"    APPLIED: arm {le.topology.value} learns reward {le.reward:.4f} "
            f"(source {le.reward_source.value}, episode {le.status.value})")
        if before is not None and isinstance(policy, LinUCBPolicy):
            b0 = np.array(before["b"][le.topology.value])
            out(f"    b[{le.topology.value}] {_vec(b0)} -> {_vec(policy.b[le.topology])}")
            out(f"    theta[{le.topology.value}] now {_vec(_theta(policy, le.topology))}")
    else:
        out(f"    REFUSED: {record.learning_rejection.value if record.learning_rejection else '-'} "
            f"(episode {le.status.value}); policy state unchanged")


def render_persistence(world: World, out: Out) -> None:
    tables = ["missions", "topology_decisions", "graph_snapshots", "allocation_plans", "outcomes",
              "events_received", "event_decisions", "episodes_trusted", "episodes_quarantined",
              "learning_events", "policy_state"]
    counts = "  ".join(f"{t}={world.repo.count(t)}" for t in tables)
    applied = world.repo.count("learning_events", "applied_at IS NOT NULL")
    out(f"[11] Persisted (SQLite, append-only): {counts}")
    out(f"     learning updates applied = {applied}; private keys stored = 0 (KeyRing is memory-only)")


# --- section 2: learning stream ----------------------------------------------


def demo_stream(n: int, settings: RunSettings, seed_base: int) -> tuple[list[tuple[Scenario, int]], int]:
    """First ``n`` generated missions (seed ``seed_base + i``, factor combos cycled over the full grid)
    that offer the policy at least two allocatable topologies (D030). Returns the stream and the
    number of candidate seeds skipped."""
    grid = factor_grid()
    stream: list[tuple[Scenario, int]] = []
    tried = 0
    while len(stream) < n:
        factors = grid[(tried * 7) % len(grid)]
        seed = seed_base + tried
        tried += 1
        scenario = generate_scenario(seed, factors)
        eligible, _, _ = feasible_topologies(scenario, settings.costs, settings.allocation)
        if len(eligible) >= 2:
            stream.append((scenario, seed))
    return stream, tried - n


def counterfactual_rewards(scenario: Scenario, seed: int, settings: RunSettings) -> dict[TopologyName, float]:
    """Evaluation-only shadow run of every allocatable topology (brief 12.3). Never reaches a learner."""
    _, _, plans = feasible_topologies(scenario, settings.costs, settings.allocation)
    rewards = {}
    for topo, (graph, plan) in plans.items():
        trace = simulate(scenario, graph, plan, seed, settings.costs)
        rewards[topo] = compute_reward(trace.metrics, settings.reward).reward
    return rewards


# --- section 3 helpers -------------------------------------------------------


def _probe_choice(policy: LinUCBPolicy, scenario: Scenario,
                  settings: RunSettings) -> tuple[TopologyName | None, dict[TopologyName, float]]:
    """What the policy would pick for this context, without changing its state."""
    from samg.context import extract_features

    ctx = extract_features(scenario)
    eligible, _, _ = feasible_topologies(scenario, settings.costs, settings.allocation)
    decision = policy.clone().select(ctx.features, eligible, ctx.feature_schema_version)
    return decision.topology, dict(decision.scores)


@dataclass
class DemoResult:
    """Structured result of the demo, for tests (deterministic)."""

    clean: MissionRunRecord | None = None
    stream: list[MissionRunRecord] = field(default_factory=list)
    protected_attack: list[MissionRunRecord] = field(default_factory=list)
    vulnerable_attack: list[MissionRunRecord] = field(default_factory=list)
    pre_attack_state: dict[str, Any] = field(default_factory=dict)
    protected_state: dict[str, Any] = field(default_factory=dict)
    vulnerable_state: dict[str, Any] = field(default_factory=dict)
    comparison: Any | None = None


def run_demo(out: Out = print, cfg: DemoConfig | None = None) -> DemoResult:
    cfg = cfg or DemoConfig()
    settings = RunSettings.load(use_cpsat=cfg.use_cpsat)
    result = DemoResult()
    learner = LinUCBPolicy(alpha=cfg.alpha, seed=cfg.policy_seed)
    world = World.create(learner, policy_instance="P3-protected")

    out(RULE)
    out("SAMG vertical slice demo  (Secure Adaptive Mission Graphs; all randomness seeded; simulated time)")
    out(f"configs: reward={settings.reward.version} topology_costs={settings.costs.version} "
        f"allocation={settings.allocation.version} security={settings.security.version}  "
        f"LinUCB alpha={cfg.alpha} lambda={learner.lam} policy_seed={cfg.policy_seed}")
    out(RULE)

    # 1 -----------------------------------------------------------------------
    out("")
    out("SECTION 1. CLEAN RUN: judge mission, protected LinUCB, every step of the loop")
    out(SUB)
    judge = judge_scenario(cfg.judge_seed)
    before = learner.snapshot()
    rec = run_single_mission(judge, world, settings, seed=cfg.judge_seed, mission_index=0)
    render_mission(rec, judge, settings, before, learner, out)
    render_persistence(world, out)
    result.clean = rec

    # 2 -----------------------------------------------------------------------
    out("")
    out(f"SECTION 2. LEARNING: {cfg.n_learn} generated missions through the same protected learner")
    out(SUB)
    full, skipped = demo_stream(cfg.n_learn + cfg.n_attack + 1, settings, cfg.stream_seed_base)
    learn, attack_stream, probe = full[:cfg.n_learn], full[cfg.n_learn:cfg.n_learn + cfg.n_attack], full[-1]
    out(f"stream: generate_scenario(seed, factors), seeds from {cfg.stream_seed_base}, factor combos cycled over "
        f"the full grid; {skipped} candidate seed(s) skipped (fewer than 2 allocatable topologies, D030)")
    out(" #  mission                    d     h     r     a    offered  pick  how      ACP reward  best(oracle)  regret")
    regrets: list[float] = []
    picks: list[TopologyName] = []
    oracle_sum: dict[TopologyName, float] = {t: 0.0 for t in TopologyName}
    oracle_n: dict[TopologyName, int] = {t: 0 for t in TopologyName}
    best_arms: list[TopologyName] = []
    for i, (sc, seed) in enumerate(learn, start=1):
        r = run_single_mission(sc, world, settings, seed=seed, mission_index=i)
        result.stream.append(r)
        cf = counterfactual_rewards(sc, seed, settings)
        for t, v in cf.items():
            oracle_sum[t] += v
            oracle_n[t] += 1
        best = max(cf, key=lambda t: (cf[t], -ARM_ORDER.index(t)))
        best_arms.append(best)
        reward = r.episode.reward if r.episode and r.episode.reward is not None else 0.0
        regret = cf[best] - cf.get(r.decision.topology, reward)
        regrets.append(regret)
        picks.append(r.decision.topology)
        f = r.context.features
        how = "warm-up" if r.decision.warmup else "UCB"
        out(f"{i:2d}  {sc.mission.mission_id[:25]:<25} {f[1]:5.2f} {f[2]:5.2f} {f[3]:5.2f} {f[4]:5.2f}   "
            f"{''.join(SHORT[t][0] for t in r.decision.eligible):<7}  {SHORT[r.decision.topology]}  {how:<7}  {reward:8.4f}    {SHORT[best]} {cf[best]:.4f}   {regret:7.4f}"
            f"   {r.episode.status.value if r.episode else '-'}")
    half = len(picks) // 2
    for label, part, reg in (("first half", picks[:half], regrets[:half]), ("second half", picks[half:], regrets[half:])):
        c = Counter(part)
        out(f"  {label:<11}: " + "  ".join(f"{SHORT[t]}={c.get(t, 0):2d}" for t in ARM_ORDER)
            + f"   mean regret {np.mean(reg):.4f}")
    wins = Counter(best_arms)
    out("  counterfactual, evaluation only (every allocatable arm shadow-run on the same seed; never learned):")
    out("    best arm per mission: " + "  ".join(f"{SHORT[t]}={wins.get(t, 0)}" for t in ARM_ORDER)
        + "   mean reward where allocatable: "
        + "  ".join(f"{SHORT[t]}={oracle_sum[t] / oracle_n[t]:.4f} (n={oracle_n[t]})" if oracle_n[t] else
                    f"{SHORT[t]}=- (n=0)" for t in ARM_ORDER))
    out("  learned theta . x for the judge mission context: "
        + "  ".join(f"{SHORT[t]}={float(_theta(learner, t) @ np.array(rec.context.features)):.4f}" for t in ARM_ORDER))
    applied = world.repo.count("learning_events", "applied_at IS NOT NULL")
    out(f"  protected updates applied: {applied} (one per ADMITTED episode); episodes not admitted: "
        f"{world.repo.count('episodes_quarantined')}")

    # 3 -----------------------------------------------------------------------
    out("")
    out("SECTION 3. ATTACK: validly signed false reports vs protected (S2) and vulnerable (S1) learners")
    out(SUB)
    pre = learner.snapshot()
    result.pre_attack_state = pre
    s2 = LinUCBPolicy.from_snapshot(pre)
    s1 = VulnerableLinUCB.from_snapshot(pre)
    w2 = World.create(s2, policy_instance="S2-protected")
    w1 = World.create(s1, mode=PolicyMode.VULNERABLE, policy_instance="S1-vulnerable")
    anatomy_index = cfg.n_learn + 1
    start = anatomy_index + 1
    attack = AttackConfig(compromised_agent=cfg.compromised_agent, preferred_topology=cfg.preferred_topology,
                          inflation=cfg.inflation, deflation=cfg.deflation,
                          schedule=frozenset({anatomy_index, *range(start, start + cfg.n_attack)}),
                          sabotage_schedule=frozenset({anatomy_index}))
    out(f"pre-attack state: the Section 2 learner after {applied} protected updates, cloned into "
        f"S2 (LinUCBPolicy) and S1 (VulnerableLinUCB)")
    out(f"attacker: {attack.compromised_agent} (registered, authorised, signs with its real key and fresh seq); "
        f"preferred topology {attack.preferred_topology.value}, fixed in advance")
    out(f"false REWARD_CLAIM = true reward + {attack.inflation} on {SHORT[attack.preferred_topology]}, "
        f"true reward - {attack.deflation} otherwise (claim derived from the run, shown next to the truth)")

    # 3a: anatomy of one attacked mission, on throwaway clones of the pre-attack state
    a2, a1 = LinUCBPolicy.from_snapshot(pre), VulnerableLinUCB.from_snapshot(pre)
    wa2 = World.create(a2, policy_instance="S2-anatomy")
    wa1 = World.create(a1, mode=PolicyMode.VULNERABLE, policy_instance="S1-anatomy")
    ra2 = run_single_mission(judge, wa2, settings, seed=cfg.judge_seed, mission_index=anatomy_index, attack=attack)
    ra1 = run_single_mission(judge, wa1, settings, seed=cfg.judge_seed, mission_index=anatomy_index, attack=attack)
    _render_attack_detail(ra2, ra1, attack, out)

    # 3b: the same attack over a window of generated missions, S1 vs S2 from the identical pre-attack state
    out("")
    out(f"3b. Attack window: {cfg.n_attack} generated missions, every one attacked (reward claim only, no sabotage).")
    out("    S1 and S2 start from the identical pre-attack state and see the same scenarios, seeds and schedule;")
    out("    each runs in its own SQLite world.")
    rows = []
    for k, (sc, seed) in enumerate(attack_stream):
        idx = start + k
        r2 = run_single_mission(sc, w2, settings, seed=seed, mission_index=idx, attack=attack)
        r1 = run_single_mission(sc, w1, settings, seed=seed, mission_index=idx, attack=attack)
        result.protected_attack.append(r2)
        result.vulnerable_attack.append(r1)
        rows.append((idx, r2, r1))
    out("")
    out(" #   S2 pick  false claim -> ACP      S2 learns   |  S1 pick  true r   claimed  S1 learns")
    for idx, r2, r1 in rows:
        false2 = [d for d in r2.final_decisions if d.event_id in r2.false_claim_event_ids]
        verdict = ",".join(sorted({d.status.value for d in false2})) or "-"
        s2r = f"{r2.learning_event.reward:.4f}" if r2.learning_applied and r2.learning_event else "none"
        s1r = f"{r1.learning_event.reward:.4f}" if r1.learning_applied and r1.learning_event else "none"
        true1 = r1.ground_truth_reward.reward if r1.ground_truth_reward else 0.0
        out(f"{idx:3d}   {SHORT[r2.decision.topology]}     {verdict:<20}    {s2r:<9}   |  "
            f"{SHORT[r1.decision.topology]}     {true1:.4f}   {r1.claimed_reward or 0.0:.4f}   {s1r}")
    c2 = Counter(r.decision.topology for _, r, _ in rows)
    c1 = Counter(r.decision.topology for _, _, r in rows)
    pref = attack.preferred_topology
    false_total = sum(len(r.false_claim_event_ids) for _, r, _ in rows)
    false_admitted = sum(1 for _, r, _ in rows for d in r.final_decisions
                         if d.event_id in r.false_claim_event_ids and d.status is EventStatus.CORROBORATED)
    honest_blocked = sum(1 for _, r, _ in rows for d in r.final_decisions
                         if d.event_id not in r.false_claim_event_ids
                         and d.signer_id != settings.security.witness.identity_id and d.status in (EventStatus.DISPUTED, EventStatus.REJECTED))
    honest_total = sum(len(r.agent_events) - len(r.false_claim_event_ids) for _, r, _ in rows)
    s1_poisoned = sum(1 for _, _, r in rows if r.attacked and r.learning_applied)
    out(f"  S2: false claims submitted {false_total}, corroborated {false_admitted}, "
        f"honest claims blocked {honest_blocked}/{honest_total}; updates used ACP-recomputed reward only")
    out(f"  S1: updates from attacker-claimed reward {s1_poisoned}/{len(rows)}")
    out(f"  picks of preferred {SHORT[pref]}: S2 {c2.get(pref, 0)}/{len(rows)}   S1 {c1.get(pref, 0)}/{len(rows)}")

    # replay
    first2, first1 = rows[0][1], rows[0][2]
    replayed = [e for e in first2.agent_events if e.event_id in first2.false_claim_event_ids
                and e.event_type is EventType.REWARD_CLAIM]
    snap2, snap1 = s2.snapshot(), s1.snapshot()
    dec2, ap2, why2 = replay_events(attack_stream[0][0], first2, w2, settings, replayed)
    dec1, ap1, why1 = replay_events(attack_stream[0][0], first1, w1, settings,
                                    [e for e in first1.agent_events if e.event_id in first1.false_claim_event_ids
                                     and e.event_type is EventType.REWARD_CLAIM])
    out("")
    out(f"Replay (brief 9.3): resubmit the attacker's signed REWARD_CLAIM {_short_id(replayed[0].event_id)} "
        f"from mission {start}")
    out(f"  S2: {dec2[0].status.value} {','.join(r.value for r in dec2[0].reason_codes)}; re-offered episode -> "
        f"{'APPLIED' if ap2 else 'refused ' + (why2.value if why2 else '-')}; state unchanged: {s2.snapshot() == snap2}")
    out(f"  S1: {dec1[0].status.value} {','.join(r.value for r in dec1[0].reason_codes)}; re-offered episode -> "
        f"{'APPLIED' if ap1 else 'refused ' + (why1.value if why1 else '-')}; state unchanged: {s1.snapshot() == snap1}")

    # divergence
    out("")
    out("Learner state after the attack window (divergence is 0 at the start: identical clones)")
    out("  arm               ||A_S1-A_S2||_F  ||b_S1-b_S2||  ||theta_S1-theta_S2||   theta.x(judge) S2 / S1")
    x = np.array(rec.context.features)
    for arm in ARM_ORDER:
        da = np.linalg.norm(s1.A[arm] - s2.A[arm])
        db = np.linalg.norm(s1.b[arm] - s2.b[arm])
        dt = np.linalg.norm(_theta(s1, arm) - _theta(s2, arm))
        out(f"  {arm.value:<16} {da:14.4f}  {db:13.4f}  {dt:20.4f}      "
            f"{float(_theta(s2, arm) @ x):.4f} / {float(_theta(s1, arm) @ x):.4f}")
    for label, sc in (("judge mission", judge), ("next unseen generated mission", probe[0])):
        t2, sc2 = _probe_choice(s2, sc, settings)
        t1, sc1 = _probe_choice(s1, sc, settings)
        out(f"  next choice for the {label}: S2 -> {t2.value if t2 else '-'}   S1 -> {t1.value if t1 else '-'}")
        out("      UCB scores  S2: " + " ".join(f"{SHORT[a]}={sc2[a]:.3f}" for a in ARM_ORDER)
            + "   S1: " + " ".join(f"{SHORT[a]}={sc1[a]:.3f}" for a in ARM_ORDER))
    result.protected_state, result.vulnerable_state = s2.snapshot(), s1.snapshot()

    # 4 -----------------------------------------------------------------------
    out("")
    out("SECTION 4. POLICY COMPARISON: fixed baselines, UCB1, LinUCB, and contextual epsilon-greedy")
    out(SUB)
    out("Short, seeded CLI demonstration on a shared scenario stream. These sample results illustrate the")
    out("comparison output; use scripts/run_experiment_epsilon_greedy.py for dev tuning and held-out results.")
    from samg.evaluation.executor import OrchestrationExecutor
    from samg.evaluation.runner import (
        EpsilonGreedyExperimentConfig,
        ExperimentConfig,
        run_experiment_a,
    )

    compare_cfg = ExperimentConfig(
        version="cli-demo-comparison-v1",
        master_seed=cfg.stream_seed_base,
        n_dev=0,
        n_train=max(9, min(cfg.comparison_train, 18)),
        n_test=max(6, min(cfg.comparison_test, 10)),
        alpha=cfg.alpha,
        lam=learner.lam,
        warmup_per_arm=1,
        frozen=True,
    )
    eps_cfg = EpsilonGreedyExperimentConfig(
        epsilon=0.2,
        epsilon_grid=(0.2,),
        lam=learner.lam,
        warmup_per_arm=1,
        policy_seeds=(cfg.policy_seed, cfg.policy_seed + 1, cfg.policy_seed + 2),
    )
    comparison_executor = OrchestrationExecutor(settings)
    comparison = run_experiment_a(compare_cfg, comparison_executor, costs=settings.costs,
                                  epsilon_greedy=eps_cfg)
    result.comparison = comparison
    out(f"sample size: {compare_cfg.n_train} training missions; {compare_cfg.n_test} evaluation missions; "
        f"P4 averaged across {len(eps_cfg.policy_seeds)} policy seeds; epsilon={eps_cfg.epsilon:.2f}")
    out("policy                         mean reward   bootstrap 95% CI          regret   selections")
    for policy in ("P0-H", "P0-F", "P0-D", "P1", "P2", "P3", "P4"):
        summary = comparison.test[policy]
        label = policy if policy != "P1" else f"P1 (best fixed {comparison.p1_topology.value})"
        ci = f"[{summary.reward.ci95_low:.4f}, {summary.reward.ci95_high:.4f}]" \
            if summary.reward.ci95_low is not None and summary.reward.ci95_high is not None else "n/a"
        selections = ", ".join(f"{arm}={count}" for arm, count in sorted(summary.selection_counts.items())) or "none"
        out(f"{label:<29} {summary.reward.mean if summary.reward.mean is not None else float('nan'):>11.4f}   "
            f"{ci:<23} {summary.regret.mean if summary.regret.mean is not None else float('nan'):>7.4f}   {selections}")
    out("paired reward differences (same evaluation missions; positive favors the first policy):")
    for item in comparison.comparisons:
        out(f"  {item.a} - {item.b}: {item.mean_diff if item.mean_diff is not None else float('nan'):+.4f} "
            f"95% CI [{item.ci95_low}, {item.ci95_high}], W/L/T={item.wins}/{item.losses}/{item.ties}, "
            f"n={item.n_pairs}")
    p4 = comparison.test["P4"]
    out(f"P4 exploratory choices: {p4.exploration_count}; realized rate={p4.exploration_rate}; "
        f"policy seeds={p4.policy_seed_count}")

    out("")
    out(RULE)
    out("Summary: a valid signature proved who sent each false report, not that it was true. The ACP disputed")
    out("every false claim against independent witness evidence and recomputed the reward; the protected learner")
    out("never consumed a claimed reward, while the vulnerable learner's parameters and choices moved toward the")
    out("attacker's topology. Trust boundary: the simulated witness is assumed honest (brief 8.5).")
    out(RULE)
    return result


def _render_attack_detail(r2: MissionRunRecord, r1: MissionRunRecord, attack: AttackConfig, out: Out) -> None:
    out("")
    sabotaged = [o for o in (r2.trace.outcomes if r2.trace else ()) if o.failure_reason == "TASK_FAILED"]
    out(f"3a. Anatomy of one attacked mission: judge mission {r2.mission_id}, run on throwaway clones of the "
        f"pre-attack state")
    out(f"    topology chosen S2={r2.decision.topology.value} S1={r1.decision.topology.value}; fault injected in the "
        f"simulator: {attack.compromised_agent} abandons "
        f"{', '.join(o.task_id for o in sabotaged) or '-'} (ground truth: FAILED)")
    final = {d.event_id: d for d in r2.final_decisions}
    auth = {d.event_id: d for d in r2.auth_decisions}
    witness_by_task: dict[str, list[WitnessEvent]] = {}
    for w in r2.witness_events:
        witness_by_task.setdefault(w.task_id, []).append(w)
    out("    ACP trace for the attacker's false events (S2 world; S1's ACP decides the same, S1 ignores it):")
    for e in r2.agent_events:
        if e.event_id not in r2.false_claim_event_ids:
            continue
        a, f = auth[e.event_id], final[e.event_id]
        what = (f"claims task {e.task_id} complete" if e.event_type is EventType.TASK_COMPLETE_CLAIM
                else f"claims reward {e.payload['claimed_reward']:.4f}")
        out(f"      {_short_id(e.event_id)} {e.event_type.value}: {what}")
        out(f"        signature+role+freshness: {a.status.value}   evidence check: {f.status.value} "
            f"({','.join(r.value for r in f.reason_codes)})")
        if isinstance(e, AgentEvent) and e.task_id:
            seen = " -> ".join(f"{w.to_state.value}@{w.sim_time_ms / MIN:.1f}min"
                               for w in witness_by_task.get(e.task_id, []))
            out(f"        witness saw {e.task_id}: {seen}")
    ep = r2.episode
    assert ep is not None
    out(f"    Episode (S2): {ep.status.value} [{','.join(r.value for r in ep.reason_codes)}]")
    failed = [t for t, s in ep.admitted_task_states.items() if s is TaskState.FAILED]
    if failed:
        out(f"      witness-verified FAILED tasks: {','.join(failed)}")
    if ep.status is EpisodeStatus.ADMITTED:
        out(f"      the witness covers every reward-critical task, so the episode is still admitted with the "
            f"ACP-recomputed reward {ep.reward:.4f};")
        out("      the false claims are quarantined and excluded")
    out(f"    S2 learns {r2.learning_event.reward:.4f} ({r2.learning_event.reward_source.value})"
        if r2.learning_applied and r2.learning_event else "    S2 learns nothing")
    if r1.learning_applied and r1.learning_event and r1.ground_truth_reward:
        out(f"    S1 learns {r1.learning_event.reward:.4f} ({r1.learning_event.reward_source.value}); "
            f"simulator ground truth was {r1.ground_truth_reward.reward:.4f}")


# --- single mission (``samg run``) ---------------------------------------------


def run_one(out: Out, *, seed: int, policy_kind: str, mode: PolicyMode, scenario_kind: str = "judge",
            alpha: float = DemoConfig.alpha, attack: bool = False, compromised: str = "A4",
            preferred: TopologyName = TopologyName.FUNCTIONAL_CELL, use_cpsat: bool = True) -> MissionRunRecord:
    """One mission in full detail (the ``run`` subcommand)."""
    from samg.learning import make_policy

    settings = RunSettings.load(use_cpsat=use_cpsat)
    scenario = judge_scenario(seed) if scenario_kind == "judge" else generate_scenario(seed)
    if mode is PolicyMode.VULNERABLE:
        if policy_kind != "linucb":
            raise ValueError("vulnerable mode is only defined for LinUCB (S1)")
        policy: TopologyPolicy = make_policy("S1", {"alpha": alpha}, seed=0)
    else:
        kind = {"linucb": "P3", "ucb1": "P2", "fixed-h": "P0-H", "fixed-f": "P0-F", "fixed-d": "P0-D"}[policy_kind]
        policy = make_policy(kind, {"alpha": alpha} if kind == "P3" else {}, seed=0)
    world = World.create(policy, mode=mode)
    atk = AttackConfig(compromised_agent=compromised, preferred_topology=preferred,
                       schedule=frozenset({0})) if attack else None
    before = policy.snapshot()
    out(RULE)
    out(f"samg run  seed={seed}  scenario={scenario_kind}  policy={policy_kind}  mode={mode.value}"
        + (f"  attack: {compromised} prefers {preferred.value}" if attack else ""))
    out(RULE)
    record = run_single_mission(scenario, world, settings, seed=seed, mission_index=0, attack=atk)
    render_mission(record, scenario, settings, before, policy, out)
    render_persistence(world, out)
    return record


__all__ = ["DemoConfig", "DemoResult", "demo_stream", "render_mission", "run_demo", "run_one"]
