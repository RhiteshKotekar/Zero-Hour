"""Thin read-only helpers for the Streamlit views (no business logic).

Every function here only *composes* existing public SAMG functions
(``run_single_mission``, ``execute_mission``, ``feasible_topologies``,
``make_policy``, ``run_experiment_a`` ...) and reshapes their records for
display. Nothing here computes a reward, a graph cost, an evidence decision, an
admission verdict or a policy update: those values are read off the records the
orchestration returns.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from samg.allocation import feasible_topologies
from samg.domain import (
    AgentEvent,
    EventStatus,
    EventType,
    PolicyMode,
    Scenario,
    TopologyEligibility,
    TopologyName,
    config_hash,
)
from samg.evaluation.attacks import AttackConfig
from samg.learning import ARM_ORDER, LinUCBPolicy, TopologyPolicy, VulnerableLinUCB, make_policy
from samg.orchestration import (
    MissionExecution,
    MissionRunRecord,
    RunSettings,
    World,
    execute_mission,
    run_single_mission,
)
from samg.simulation.scenarios import ScenarioFactors, factor_grid, generate_scenario, judge_scenario

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = REPO_ROOT / "artifacts" / "experiments"
MIN = 60_000.0

# Saved demo configuration (the "reset" target). Matches ``samg demo`` / docs/DEMO.md.
DEMO_DEFAULTS: dict[str, Any] = {
    "seed": 7,
    "scenario_kind": "judge",
    "policy": "linucb",
    "mode": "adaptive",
    "fixed_topology": TopologyName.HIERARCHICAL.value,
    "alpha": 0.3,
    "use_cpsat": True,
    "factors": ScenarioFactors().model_dump(),
    "attack_agent": "A4",
    "attack_preferred": TopologyName.FUNCTIONAL_CELL.value,
    "n_pre": 12,
    "n_attack": 6,
}
FACTOR_CHOICES: dict[str, tuple[str, ...]] = {
    name: tuple(sorted({getattr(f, name) for f in factor_grid()})) for name in ScenarioFactors.model_fields
}
POLICY_KINDS = {"linucb": "P3", "ucb1": "P2"}
FIXED_KINDS = {TopologyName.HIERARCHICAL: "P0-H", TopologyName.FUNCTIONAL_CELL: "P0-F",
               TopologyName.DISTRIBUTED: "P0-D"}


# --- settings ------------------------------------------------------------------


def load_settings(use_cpsat: bool = True) -> RunSettings:
    return RunSettings.load(use_cpsat=use_cpsat)


def config_id(settings: RunSettings) -> str:
    """Stable hash of every config that shapes a mission run (costs, allocation, reward, security)."""
    return config_hash(settings.costs, settings.allocation, settings.reward, settings.security)


def config_versions(settings: RunSettings) -> dict[str, str]:
    return {"reward": settings.reward.version, "topology_costs": settings.costs.version,
            "allocation": settings.allocation.version, "security": settings.security.version}


def build_scenario(kind: str, seed: int, factors: dict[str, str] | None = None) -> Scenario:
    if kind == "judge":
        return judge_scenario(seed)
    return generate_scenario(seed, ScenarioFactors(**(factors or {})))


# --- View 1: one mission ---------------------------------------------------------


@dataclass
class MissionRun:
    record: MissionRunRecord
    scenario: Scenario
    settings: RunSettings
    config_id: str
    policy_before: dict[str, Any]
    policy_after: dict[str, Any]
    label: str


def make_mission_policy(policy: str, mode: str, alpha: float, fixed_topology: TopologyName | None) -> TopologyPolicy:
    """Policy factory for the UI. Fixed mode uses a fixed-topology policy, so it never updates LinUCB."""
    if mode == "fixed":
        assert fixed_topology is not None
        return make_policy(FIXED_KINDS[fixed_topology])
    kind = POLICY_KINDS[policy]
    return make_policy(kind, {"alpha": alpha} if kind == "P3" else {}, seed=0)


def run_mission(*, seed: int, scenario_kind: str, factors: dict[str, str] | None, policy: str, mode: str,
                alpha: float, use_cpsat: bool, fixed_topology: TopologyName | None = None) -> MissionRun:
    """One mission through ``run_single_mission`` with a fresh protected world (in-memory SQLite)."""
    settings = load_settings(use_cpsat)
    scenario = build_scenario(scenario_kind, seed, factors)
    pol = make_mission_policy(policy, mode, alpha, fixed_topology)
    world = World.create(pol, mode=PolicyMode.PROTECTED)
    before = pol.snapshot()
    record = run_single_mission(scenario, world, settings, seed=seed, mission_index=0)
    label = (f"fixed {fixed_topology.value}" if mode == "fixed" else f"adaptive {pol.kind}")
    return MissionRun(record=record, scenario=scenario, settings=settings, config_id=config_id(settings),
                      policy_before=before, policy_after=pol.snapshot(), label=label)


@dataclass
class TopologyComparison:
    """Shadow evaluation: every eligible topology executed on the same mission and seed. Never learned."""

    verdicts: dict[TopologyName, TopologyEligibility]
    executions: dict[TopologyName, MissionExecution] = field(default_factory=dict)


def compare_topologies(scenario: Scenario, seed: int, settings: RunSettings) -> TopologyComparison:
    _, verdicts, plans = feasible_topologies(scenario, settings.costs, settings.allocation)
    out = TopologyComparison(verdicts=verdicts)
    for topo, (graph, plan) in plans.items():
        out.executions[topo] = execute_mission(
            scenario, topo, settings, seed=seed, decision_id=f"shadow/{scenario.mission.mission_id}/{topo.value}",
            graph=graph, plan=plan)
    return out


def comparison_rows(cmp: TopologyComparison) -> list[dict[str, Any]]:
    rows = []
    for topo in TopologyName:
        v = cmp.verdicts[topo]
        ex = cmp.executions.get(topo)
        if ex is None:
            rows.append({"topology": topo.value, "eligible": False,
                         "reason": ",".join(r.value for r in v.reasons) + (f" ({v.detail})" if v.detail else "")})
            continue
        m = ex.trace.metrics if ex.trace else None
        cross = [h for h in ex.plan.handoffs if h.hops > 0]
        rows.append({
            "topology": topo.value, "eligible": True, "reason": "",
            "coordinators": ",".join(ex.graph.coordinators) or "-",
            "links": len(ex.graph.coordination_links()),
            "cross-agent handoffs": len(cross), "total hops": sum(h.hops for h in cross),
            "handoff cost": round(sum(h.cost for h in cross), 4),
            "makespan (min)": round(m.makespan / MIN, 2) if m else None,
            "coordination cost": round(m.coordination_cost, 4) if m else None,
            "completion C": round(m.weighted_completion, 4) if m else None,
            "ground-truth reward": round(ex.ground_truth_reward.reward, 4),
            "episode": ex.episode.status.value,
            "ACP reward": None if ex.episode.reward is None else round(ex.episode.reward, 4),
        })
    return rows


# --- record -> display rows (pure reshaping) -----------------------------------------


def eligibility_rows(record: MissionRunRecord) -> list[dict[str, Any]]:
    return [{"topology": t.value, "eligible": v.eligible,
             "reasons": ",".join(r.value for r in v.reasons), "detail": v.detail}
            for t, v in ((t, record.eligibility[t]) for t in TopologyName)]


def score_rows(record: MissionRunRecord) -> list[dict[str, Any]]:
    d = record.decision
    rows = []
    for arm in ARM_ORDER:
        rows.append({"topology": arm.value, "offered": arm in d.eligible,
                     "estimated value (mean)": d.means.get(arm), "confidence bonus": d.bonuses.get(arm),
                     "score": d.scores.get(arm), "selected": arm is d.topology})
    return rows


def assignment_rows(record: MissionRunRecord, scenario: Scenario) -> list[dict[str, Any]]:
    if record.plan is None:
        return []
    tasks = {t.task_id: t for t in scenario.mission.tasks}
    outcomes = {o.task_id: o for o in record.trace.outcomes} if record.trace else {}
    final_states = record.episode.admitted_task_states if record.episode else {}
    rows = []
    for a in record.plan.assignments:
        o = outcomes.get(a.task_id)
        t = tasks.get(a.task_id)
        rows.append({
            "task": a.task_id, "agent": a.agent_id,
            "required capability": ("|" if t and t.capability_match.value == "ANY" else "&").join(
                t.required_capabilities) if t else "",
            "predecessors": ",".join(t.dependencies) if t else "",
            "planned start (min)": round(a.start / MIN, 2), "planned end (min)": round(a.end / MIN, 2),
            "actual start (min)": None if o is None or o.start is None else round(o.start / MIN, 2),
            "actual end (min)": None if o is None or o.end is None else round(o.end / MIN, 2),
            "completed (ground truth)": None if o is None else o.completed,
            "failure": None if o is None else o.failure_reason,
            "ACP-admitted state": str(final_states[a.task_id]) if a.task_id in final_states else None,
        })
    return rows


def handoff_rows(record: MissionRunRecord) -> list[dict[str, Any]]:
    if record.plan is None:
        return []
    return [{"dependency": f"{h.prerequisite_task}->{h.dependent_task}", "from": h.from_agent, "to": h.to_agent,
             "path": " > ".join(h.path), "hops": h.hops, "cost": h.cost, "delay (min)": h.delay / MIN}
            for h in record.plan.handoffs]


def reward_rows(record: MissionRunRecord) -> list[dict[str, Any]]:
    rb, m = record.acp_reward, record.acp_metrics
    if rb is None or m is None:
        return []
    raw = {"completion": ("C", f"weighted completion {m.weighted_completion:.4f}", m.weighted_completion),
           "duration": ("T", f"makespan {m.makespan / MIN:.2f} min", m.duration_norm),
           "resources": ("R", f"resource used {m.resource_used:.2f}", m.resource_norm),
           "coordination": ("H", f"coordination cost {m.coordination_cost:.4f}", m.coordination_norm)}
    rows = []
    for key in rb.weights:
        sym, desc, norm = raw.get(key, (key, "", None))
        rows.append({"term": key, "raw measured": desc, "normalised": norm,
                     "enters formula as": sym if sym == "C" else f"1-{sym}", "term value": rb.components.get(key),
                     "weight": rb.weights[key], "contribution": rb.contributions.get(key)})
    return rows


def event_rows(record: MissionRunRecord) -> list[dict[str, Any]]:
    """Per-event validation trace: signature/role/freshness stage, then evidence stage."""
    auth = {d.event_id: d for d in record.auth_decisions}
    final = {d.event_id: d for d in record.final_decisions}
    events: list[Any] = [*record.witness_events, *record.agent_events]
    rows = []
    for e in events:
        a, f = auth.get(e.event_id), final.get(e.event_id)
        is_agent = isinstance(e, AgentEvent)
        claim = e.payload.get("claimed_reward") if is_agent and e.event_type is EventType.REWARD_CLAIM else None
        rows.append({
            "event": e.event_id, "signer": e.signer_id, "type": e.event_type.value, "task": e.task_id or "-",
            "auth stage": a.status.value if a else "-",
            "auth reasons": ",".join(r.value for r in a.reason_codes) if a else "",
            "evidence stage": f.status.value if f else "-",
            "evidence reasons": ",".join(r.value for r in f.reason_codes) if f else "",
            "claimed reward": claim,
            "false claim (oracle)": e.event_id in record.false_claim_event_ids,
        })
    return rows


def status_counts(decisions: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in decisions:
        out[d.status.value] = out.get(d.status.value, 0) + 1
    return dict(sorted(out.items()))


# --- View 2: experiment results ---------------------------------------------------------


def saved_files(pattern: str) -> list[Path]:
    return sorted(ARTIFACTS.glob(pattern)) if ARTIFACTS.exists() else []


class ExperimentLoadError(Exception):
    """Raised when a saved experiment artifact cannot be loaded as a full ExperimentResult."""


def load_experiment_result(path: Path) -> Any:
    """Load a full ``ExperimentResult`` from *path*.

    Raises ``ExperimentLoadError`` with a human-readable message if the file is
    missing, contains malformed JSON, or holds only a legacy summary produced by
    ``summary_json()`` (which lacks ``training_rewards`` and ``records``).
    """
    from samg.evaluation.runner import ExperimentResult

    if not path.exists():
        raise ExperimentLoadError(
            f"Experiment artifact not found: {path}\n\n"
            "Run `python scripts/run_experiment_a.py` to generate it."
        )
    text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExperimentLoadError(
            f"Malformed JSON in {path.name}: {exc}\n\n"
            "The file may be corrupted. Re-run the experiment to regenerate it."
        ) from exc

    # Detect legacy summary-only artifacts: they contain a 'table' key and
    # lack the 'training_rewards' key that a full ExperimentResult has.
    if isinstance(raw, dict) and "table" in raw and "training_rewards" not in raw:
        raise ExperimentLoadError(
            f"{path.name} contains a human-readable summary, not a full ExperimentResult.\n\n"
            "This was generated by an older version of the experiment runner that wrote\n"
            "only the summary to this path. Re-run `python scripts/run_experiment_a.py`\n"
            "to produce both the full artifact (experiment_a.json) and the summary\n"
            "(experiment_a_summary.json)."
        )

    try:
        return ExperimentResult.model_validate(raw)
    except Exception as exc:
        raise ExperimentLoadError(
            f"Cannot parse {path.name} as ExperimentResult: {exc}\n\n"
            "The file may be from an incompatible version. Re-run the experiment to\n"
            "regenerate it."
        ) from exc


def find_executor() -> tuple[Any, str]:
    """Return ``(executor_factory, source)``. Prefers ``samg.evaluation.executor.OrchestrationExecutor``.

    If that module is absent, falls back to a thin dashboard adapter over ``execute_mission``
    (no persistence) so development mode still works; the source string says which.
    """
    try:
        from samg.evaluation.executor import OrchestrationExecutor  # type: ignore[import-not-found]
    except ImportError:
        return _DashboardExecutor, "samg.dashboard.data._DashboardExecutor (fallback adapter over execute_mission)"
    return OrchestrationExecutor, "samg.evaluation.executor.OrchestrationExecutor"


class _DashboardExecutor:
    """``MissionExecutor`` adapter: ``execute_mission`` -> ``MissionResult``. Read-only composition."""

    def __init__(self, settings: RunSettings | None = None) -> None:
        self.settings = settings or load_settings(use_cpsat=False)

    def execute(self, scenario: Scenario, topology: TopologyName, *, seed: int, decision_id: str) -> Any:
        from samg.evaluation.runner import MissionResult

        ex = execute_mission(scenario, topology, self.settings, seed=seed, decision_id=decision_id)
        return MissionResult(feasible=ex.feasible,
                             ground_truth_reward=ex.ground_truth_reward.reward if ex.feasible else None,
                             episode=ex.episode, metrics=ex.metrics_dict(), detail=ex.plan.detail)


def run_dev_experiment(n_train: int = 6, n_test: int = 4) -> tuple[Any, str]:
    """Tiny live Experiment A/B for development mode only (never a held-out claim)."""
    from samg.evaluation.runner import ExperimentConfig, run_experiment_a

    factory, source = find_executor()
    settings = load_settings(use_cpsat=False)
    try:
        executor = factory(settings)
    except TypeError:
        executor = factory()
    cfg = ExperimentConfig(version="exp-dev-dashboard", n_dev=0, n_train=n_train, n_test=n_test, warmup_per_arm=1)
    return run_experiment_a(cfg, executor, costs=settings.costs), source


def policy_rows(result: Any) -> list[dict[str, Any]]:
    rows = []
    for row in result.table():
        lo, hi = row["ci95"]
        rows.append({"policy": row["policy"], "n": row["n"], "mean reward": row["mean_reward"], "std": row["std"],
                     "95% CI low": lo, "95% CI high": hi, "not applicable": row["not_applicable"],
                     "infeasible": row["infeasible"], "mean oracle regret": row["mean_regret"]})
    return rows


# --- View 3: attack comparison ----------------------------------------------------------


@dataclass
class AttackRun:
    config_id: str
    attack: AttackConfig
    pre_updates: int
    anatomy_s2: MissionRunRecord
    anatomy_s1: MissionRunRecord
    window: list[tuple[MissionRunRecord, MissionRunRecord]]
    pre_state: dict[str, Any]
    s2_state: dict[str, Any]
    s1_state: dict[str, Any]
    divergence: list[dict[str, Any]]
    next_choice: dict[str, dict[str, Any]]
    judge_seed: int
    stream_seed_base: int


def _next_choice(policy: LinUCBPolicy, scenario: Scenario, settings: RunSettings) -> dict[str, Any]:
    from samg.context import extract_features

    ctx = extract_features(scenario)
    eligible, _, _ = feasible_topologies(scenario, settings.costs, settings.allocation)
    d = policy.clone().select(ctx.features, eligible, ctx.feature_schema_version)
    return {"topology": d.topology.value if d.topology else None,
            "scores": {a.value: d.scores[a] for a in ARM_ORDER if a in d.scores}}


def run_attack_comparison(*, n_pre: int, n_attack: int, compromised: str = "A4",
                          preferred: TopologyName = TopologyName.FUNCTIONAL_CELL, alpha: float = 0.3,
                          judge_seed: int = 7, stream_seed_base: int = 5000) -> AttackRun:
    """Same protocol as ``samg demo`` section 3, sized for the UI.

    A protected LinUCB learns on ``n_pre`` generated missions; its state is cloned into S2
    (protected) and S1 (``VulnerableLinUCB``, Experiment C only), and both see the same attacked
    missions in separate worlds.
    """
    from samg.demo import demo_stream

    settings = load_settings(use_cpsat=False)
    stream, _ = demo_stream(n_pre + n_attack + 1, settings, stream_seed_base)
    pre_stream, attack_stream, probe = stream[:n_pre], stream[n_pre:n_pre + n_attack], stream[-1]
    learner = LinUCBPolicy(alpha=alpha, seed=0)
    world = World.create(learner, policy_instance="P3-pre")
    for i, (sc, seed) in enumerate(pre_stream):
        run_single_mission(sc, world, settings, seed=seed, mission_index=i)
    pre = learner.snapshot()
    pre_updates = world.repo.count("learning_events", "applied_at IS NOT NULL")
    anatomy = n_pre
    start = anatomy + 1
    attack = AttackConfig(compromised_agent=compromised, preferred_topology=preferred,
                          schedule=frozenset({anatomy, *range(start, start + n_attack)}),
                          sabotage_schedule=frozenset({anatomy}))
    judge = judge_scenario(judge_seed)
    a2, a1 = LinUCBPolicy.from_snapshot(pre), VulnerableLinUCB.from_snapshot(pre)
    ra2 = run_single_mission(judge, World.create(a2, policy_instance="S2-anatomy"), settings, seed=judge_seed,
                             mission_index=anatomy, attack=attack)
    ra1 = run_single_mission(judge, World.create(a1, mode=PolicyMode.VULNERABLE, policy_instance="S1-anatomy"),
                             settings, seed=judge_seed, mission_index=anatomy, attack=attack)
    s2, s1 = LinUCBPolicy.from_snapshot(pre), VulnerableLinUCB.from_snapshot(pre)
    w2 = World.create(s2, policy_instance="S2-protected")
    w1 = World.create(s1, mode=PolicyMode.VULNERABLE, policy_instance="S1-vulnerable")
    window = []
    for k, (sc, seed) in enumerate(attack_stream):
        idx = start + k
        r2 = run_single_mission(sc, w2, settings, seed=seed, mission_index=idx, attack=attack)
        r1 = run_single_mission(sc, w1, settings, seed=seed, mission_index=idx, attack=attack)
        window.append((r2, r1))
    divergence = [{"arm": arm.value,
                   "||A_S1-A_S2||_F": float(np.linalg.norm(s1.A[arm] - s2.A[arm])),
                   "||b_S1-b_S2||": float(np.linalg.norm(s1.b[arm] - s2.b[arm])),
                   "||theta_S1-theta_S2||": float(np.linalg.norm(s1.theta(arm) - s2.theta(arm)))}
                  for arm in ARM_ORDER]
    next_choice = {}
    for label, sc in (("judge mission", judge), ("next unseen generated mission", probe[0])):
        next_choice[label] = {"S2": _next_choice(s2, sc, settings), "S1": _next_choice(s1, sc, settings)}
    return AttackRun(config_id=config_id(settings), attack=attack, pre_updates=pre_updates, anatomy_s2=ra2,
                     anatomy_s1=ra1, window=window, pre_state=pre, s2_state=s2.snapshot(), s1_state=s1.snapshot(),
                     divergence=divergence, next_choice=next_choice, judge_seed=judge_seed,
                     stream_seed_base=stream_seed_base)


def window_rows(run: AttackRun) -> list[dict[str, Any]]:
    rows = []
    for r2, r1 in run.window:
        false2 = [d for d in r2.final_decisions if d.event_id in r2.false_claim_event_ids]
        rows.append({
            "mission #": r2.mission_index, "mission": r2.mission_id,
            "S2 pick": r2.decision.topology.value if r2.decision.topology else None,
            "false claims -> ACP": ",".join(sorted({d.status.value for d in false2})) or "-",
            "S2 update applied": r2.learning_applied,
            "S2 learned reward": r2.learning_event.reward if r2.learning_applied and r2.learning_event else None,
            "S2 reward source": r2.learning_event.reward_source.value if r2.learning_event else None,
            "S1 pick": r1.decision.topology.value if r1.decision.topology else None,
            "S1 true reward": r1.ground_truth_reward.reward if r1.ground_truth_reward else None,
            "S1 claimed reward": r1.claimed_reward,
            "S1 update applied": r1.learning_applied,
            "S1 learned reward": r1.learning_event.reward if r1.learning_applied and r1.learning_event else None,
        })
    return rows


def attack_summary(run: AttackRun, settings_witness_id: str) -> dict[str, Any]:
    s2 = [r2 for r2, _ in run.window]
    false_total = sum(len(r.false_claim_event_ids) for r in s2)
    false_corroborated = sum(1 for r in s2 for d in r.final_decisions
                             if d.event_id in r.false_claim_event_ids and d.status is EventStatus.CORROBORATED)
    honest_blocked = sum(1 for r in s2 for d in r.final_decisions
                         if d.event_id not in r.false_claim_event_ids and d.signer_id != settings_witness_id
                         and d.status in (EventStatus.DISPUTED, EventStatus.REJECTED))
    honest_total = sum(len(r.agent_events) - len(r.false_claim_event_ids) for r in s2)
    pref = run.attack.preferred_topology
    return {
        "false claims submitted": false_total, "false claims corroborated (S2 ACP)": false_corroborated,
        "honest claims blocked": f"{honest_blocked}/{honest_total}",
        "S2 updates applied": sum(r.learning_applied for r in s2),
        "S1 updates from claimed reward": sum(1 for _, r in run.window if r.attacked and r.learning_applied),
        f"S2 picks of {pref.value}": sum(r.decision.topology is pref for r in s2),
        f"S1 picks of {pref.value}": sum(r.decision.topology is pref for _, r in run.window),
        "missions in window": len(run.window),
    }


def load_saved_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "ARTIFACTS", "DEMO_DEFAULTS", "ExperimentLoadError", "FACTOR_CHOICES", "AttackRun", "MissionRun",
    "TopologyComparison",
    "assignment_rows", "attack_summary", "build_scenario", "compare_topologies", "comparison_rows", "config_id",
    "config_versions", "eligibility_rows", "event_rows", "find_executor", "handoff_rows", "load_experiment_result",
    "load_saved_json", "load_settings", "policy_rows", "reward_rows", "run_attack_comparison",
    "run_dev_experiment", "run_mission", "saved_files", "score_rows", "status_counts", "window_rows",
]
