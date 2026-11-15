"""Experiment C — can a validly signed false report poison the learner? (brief §12.5; owner: Dev B).

Protocol (one run, everything seeded):

1. **Warm-up.** A protected LinUCB learns on a clean stream of *training*
   missions. Its state is saved once (``pre_state``).
2. **Clones.** ``pre_state`` is restored into
   * ``S1`` — ``VulnerableLinUCB``: signature, role and freshness checks kept,
     no evidence gate, learns the last authenticated agent-claimed reward;
   * ``S2`` — protected ``LinUCBPolicy`` behind the full ACP;
   * ``R``  — protected LinUCB on the same stream with **no attack** (reference).
   Each runs in its own SQLite world.
3. **Attack phase.** All three see the same mission contexts and seeds. At
   corruption level ``p`` a deterministic schedule (seeded) marks
   ``round(p * n_attack)`` stream positions as attacked; there the compromised
   but authorised agent signs, with its real key and fresh sequence numbers, an
   inflated (preferred topology) or deflated (other topologies) ``REWARD_CLAIM``
   plus false completion claims for any of its own tasks that really failed.
   The corruption level is a *scenario configuration*, not a measured rate.
4. **Clean follow-up.** The three post-attack states are frozen and asked to
   choose a topology for the same clean follow-up contexts; each choice is
   scored by simulator ground truth (never shown to a learner).
5. **Missing evidence.** The witness stream is withheld entirely on clean
   missions: episodes are PROVISIONAL and the protected learner must apply zero
   updates (safe non-learning), while the vulnerable learner still learns.
6. **Replay (Experiment D).** Accepted signed events are resubmitted to S2's
   world, and re-signed under an obsolete epoch; both must be refused with zero
   duplicate policy updates.

The evaluation harness knows which reports were seeded as unsupported (oracle
labels from ``ReportDraft.false_claim``); the ACP only sees its evidence.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import Field

from samg.allocation import feasible_topologies
from samg.assurance.admission import admit_episode, open_session, validate_event
from samg.assurance.freshness import InMemorySeenStore
from samg.assurance.identity import IdentityRegistry
from samg.context import extract_features
from samg.domain import (
    EpisodeStatus,
    EventStatus,
    IneligibleLearningEvent,
    LearningEvent,
    PolicyMode,
    RewardSource,
    SamgModel,
    Scenario,
    TopologyName,
)
from samg.evaluation.attacks import AttackConfig
from samg.evaluation.metrics import paired_comparison, summarize
from samg.learning import ARM_ORDER, LinUCBPolicy, VulnerableLinUCB
from samg.orchestration import (
    MissionRunRecord,
    RunSettings,
    World,
    execute_mission,
    receipt_order,
    replay_events,
    run_stream,
)
from samg.simulation import compute_reward
from samg.simulation import run as simulate
from samg.simulation.scenarios import factor_grid, generate_scenario, seed_splits

EXPERIMENT_C_VERSION = "expc-v1"
BLOCKED = frozenset({EventStatus.REJECTED, EventStatus.STALE, EventStatus.DUPLICATE, EventStatus.DISPUTED})
"""Final statuses that keep a report out of trusted learning (PROVISIONAL is counted separately)."""
REWARD_TOL = 1e-6


class ExperimentCConfig(SamgModel):
    """The ``attack:`` section of ``config/security_policy.yaml`` (never read by the ACP)."""

    version: str = "attack-v1"
    master_seed: int = 4242
    schedule_seed: int = 17
    bootstrap_seed: int = 7
    compromised_agent: str = "A1"
    preferred_topology: TopologyName = TopologyName.DISTRIBUTED
    inflation: float = Field(default=0.2, ge=0, le=1)
    deflation: float = Field(default=0.3, ge=0, le=1)
    corruption_levels: tuple[float, ...] = (0.0, 0.2, 0.4)
    n_warmup: int = Field(default=30, ge=1)
    n_dev_attack: int = Field(default=10, ge=1)
    n_dev_followup: int = Field(default=10, ge=1)
    n_attack: int = Field(default=20, ge=1)
    n_followup: int = Field(default=20, ge=1)
    n_missing_evidence: int = Field(default=10, ge=0)
    n_replay: int = Field(default=5, ge=0)
    alpha: float = Field(default=0.5, ge=0)
    lam: float = Field(default=1.0, gt=0)
    warmup_per_arm: int = Field(default=2, ge=0)
    use_cpsat: bool = True
    tuning_magnitudes: tuple[tuple[float, float], ...] = ((0.2, 0.3), (0.4, 0.5), (0.6, 0.7))
    tuning_shift_threshold: float = Field(default=0.2, ge=0, le=1)
    frozen: bool = False
    frozen_hash: str | None = None

    def attack_hash(self) -> str:
        """Hash of every field that defines the attack and the run (not the freeze bookkeeping)."""
        data = self.model_dump(mode="json", exclude={"frozen", "frozen_hash"})
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def load_experiment_c(path: str | Path | None = None) -> ExperimentCConfig:
    import yaml

    from samg.assurance.policy import DEFAULT_POLICY_PATH

    with Path(path or DEFAULT_POLICY_PATH).open(encoding="utf-8") as fh:
        return ExperimentCConfig.model_validate((yaml.safe_load(fh) or {}).get("attack") or {})


# --- scenarios and schedule ----------------------------------------------------


def scenario_sets(cfg: ExperimentCConfig) -> dict[str, list[tuple[Scenario, int]]]:
    """Disjoint ``warmup`` (train), ``dev_attack``/``dev_followup`` and ``attack``/``followup`` (test) streams."""
    n_dev = cfg.n_dev_attack + cfg.n_dev_followup
    n_test = cfg.n_attack + cfg.n_followup + cfg.n_missing_evidence
    seeds = seed_splits(cfg.master_seed, n_dev, cfg.n_warmup, n_test)
    grid = factor_grid()
    rng = np.random.default_rng(cfg.master_seed + 1)

    def build(ss: Sequence[int]) -> list[tuple[Scenario, int]]:
        picks = rng.integers(0, len(grid), size=len(ss))
        return [(generate_scenario(s, grid[int(i)]), s) for s, i in zip(ss, picks)]

    dev, test = build(seeds["dev"]), build(seeds["test"])
    a, f = cfg.n_attack, cfg.n_attack + cfg.n_followup
    return {"warmup": build(seeds["train"]), "dev_attack": dev[:cfg.n_dev_attack],
            "dev_followup": dev[cfg.n_dev_attack:], "attack": test[:a], "followup": test[a:f],
            "missing_evidence": test[f:]}


def attack_schedule(level: float, n: int, seed: int) -> frozenset[int]:
    """``round(level * n)`` attacked stream positions, chosen by a seeded permutation (nested across levels)."""
    order = np.random.default_rng(seed).permutation(n)
    return frozenset(int(i) for i in order[: int(round(level * n))])


def make_attack(cfg: ExperimentCConfig, level: float, n: int, *, inflation: float | None = None,
                deflation: float | None = None, preferred: TopologyName | None = None) -> AttackConfig:
    return AttackConfig(compromised_agent=cfg.compromised_agent,
                        preferred_topology=preferred or cfg.preferred_topology,
                        inflation=cfg.inflation if inflation is None else inflation,
                        deflation=cfg.deflation if deflation is None else deflation,
                        schedule=attack_schedule(level, n, cfg.schedule_seed))


# --- policy state --------------------------------------------------------------


def warm_up(cfg: ExperimentCConfig, settings: RunSettings, stream: Sequence[tuple[Scenario, int]]) -> dict[str, Any]:
    """Clean protected warm-up on training missions; returns the single pre-attack state."""
    policy = LinUCBPolicy(seed=cfg.master_seed, alpha=cfg.alpha, lam=cfg.lam, warmup_per_arm=cfg.warmup_per_arm)
    run_stream(stream, World.create(policy, policy_instance="warmup"), settings)
    return policy.snapshot()


def _theta(state: dict[str, Any], arm: TopologyName) -> np.ndarray:
    return np.linalg.solve(np.array(state["A"][arm.value]), np.array(state["b"][arm.value]))


def divergence(x: dict[str, Any], y: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Per arm: Frobenius ‖A_x − A_y‖, L2 ‖b_x − b_y‖ and ‖θ_x − θ_y‖."""
    out = {}
    for arm in ARM_ORDER:
        out[arm.value] = {
            "A_fro": float(np.linalg.norm(np.array(x["A"][arm.value]) - np.array(y["A"][arm.value]))),
            "b_l2": float(np.linalg.norm(np.array(x["b"][arm.value]) - np.array(y["b"][arm.value]))),
            "theta_l2": float(np.linalg.norm(_theta(x, arm) - _theta(y, arm))),
        }
    return out


# --- attack-phase accounting ----------------------------------------------------


def report_counts(records: Sequence[MissionRunRecord], mode: PolicyMode) -> dict[str, Any]:
    """Security counts with denominators for one learner's attack-phase stream.

    * unsupported report = oracle-labelled false claim; *admitted to learning*
      when it fed an applied update: S1 (no evidence gate) — authenticated in an
      episode whose update used the agent-claimed reward; S2 — final status
      CORROBORATED in an applied episode (the evidence gate accepted it).
    * legitimate report = every other agent report. *Incorrectly blocked*: S1 —
      refused at authentication/freshness (its only gate); S2 — final status in
      REJECTED/STALE/DUPLICATE/DISPUTED. PROVISIONAL is counted separately.
    * manipulated update = an applied update whose learned reward differs from
      the simulator ground-truth reward by more than 1e-6.
    """
    c: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for r in records:
        auth = {d.event_id: d for d in r.auth_decisions}
        final = {d.event_id: d for d in r.final_decisions}
        false_ids = set(r.false_claim_event_ids)
        applied = r.learning_applied
        from_claim = applied and r.learning_event is not None and r.learning_event.reward_source is RewardSource.AGENT_CLAIM
        c["missions"] += 1
        c["attacked_missions"] += int(r.attacked)
        c["episodes_admitted"] += int(r.episode is not None and r.episode.status is EpisodeStatus.ADMITTED)
        c["updates_applied"] += int(applied)
        c["updates_from_agent_claim"] += int(from_claim)
        if r.episode is not None:
            for rc in r.episode.reason_codes:
                reasons[f"episode:{rc.value}"] += 1
        if applied and r.learning_event is not None and r.ground_truth_reward is not None:
            manipulated = abs(float(r.learning_event.reward) - r.ground_truth_reward.reward) > REWARD_TOL
            c["manipulated_updates"] += int(manipulated)
            c["manipulated_updates_in_attacked"] += int(manipulated and r.attacked)
        for ev in r.agent_events:
            a, f = auth[ev.event_id], final[ev.event_id]
            for rc in f.reason_codes:
                reasons[f"{f.status.value}:{rc.value}"] += 1
            if ev.event_id in false_ids:
                c["unsupported_submitted"] += 1
                c["unsupported_authenticated"] += int(a.status is EventStatus.AUTHENTICATED)
                c[f"unsupported_final_{f.status.value}"] += 1
                if mode is PolicyMode.VULNERABLE:
                    c["unsupported_admitted"] += int(from_claim and a.status is EventStatus.AUTHENTICATED)
                else:
                    c["unsupported_admitted"] += int(applied and f.status is EventStatus.CORROBORATED)
            else:
                c["legit_submitted"] += 1
                c["legit_authenticated"] += int(a.status is EventStatus.AUTHENTICATED)
                c[f"legit_final_{f.status.value}"] += 1
                if mode is PolicyMode.VULNERABLE:
                    c["legit_blocked"] += int(a.status is not EventStatus.AUTHENTICATED)
                else:
                    c["legit_blocked"] += int(f.status in BLOCKED)
                c["legit_provisional"] += int(f.status is EventStatus.PROVISIONAL)
    c.setdefault("unsupported_admitted", 0)
    c.setdefault("legit_blocked", 0)
    c.setdefault("manipulated_updates", 0)
    out: dict[str, Any] = dict(c)
    out["frr"] = c["legit_blocked"] / c["legit_submitted"] if c["legit_submitted"] else None
    out["unsupported_admission_rate"] = (c["unsupported_admitted"] / c["unsupported_submitted"]
                                         if c["unsupported_submitted"] else None)
    out["reason_codes"] = dict(sorted(reasons.items()))
    return out


# --- clean follow-up evaluation -------------------------------------------------


class GroundTruthOracle:
    """Simulator ground-truth reward per (follow-up mission, topology), cached. Evaluation only."""

    def __init__(self, settings: RunSettings) -> None:
        self.settings = settings
        self._eligible: dict[str, tuple[list[TopologyName], dict]] = {}
        self._reward: dict[tuple[str, TopologyName], float] = {}

    def eligible(self, scenario: Scenario) -> tuple[list[TopologyName], dict]:
        key = scenario.scenario_id
        if key not in self._eligible:
            arms, _, plans = feasible_topologies(scenario, self.settings.costs, self.settings.allocation)
            self._eligible[key] = (arms, plans)
        return self._eligible[key]

    def reward(self, scenario: Scenario, seed: int, topology: TopologyName) -> float:
        key = (scenario.scenario_id, topology)
        if key not in self._reward:
            graph, plan = self.eligible(scenario)[1][topology]
            trace = simulate(scenario, graph, plan, seed, self.settings.costs)
            self._reward[key] = compute_reward(trace.metrics, self.settings.reward).reward
        return self._reward[key]


def frozen_choices(state: dict[str, Any], cls: type[LinUCBPolicy], stream: Sequence[tuple[Scenario, int]],
                   oracle: GroundTruthOracle) -> list[dict[str, Any]]:
    """Choice and ground-truth reward of a frozen copy of ``state`` on each clean follow-up mission."""
    out = []
    for scenario, seed in stream:
        policy = cls.from_snapshot(state)  # fresh copy: select() never mutates the evaluated state
        ctx = extract_features(scenario)
        arms, _ = oracle.eligible(scenario)
        decision = policy.select(ctx.features, arms, ctx.feature_schema_version)
        topo = decision.topology
        out.append({"mission_id": scenario.mission.mission_id, "topology": None if topo is None else topo.value,
                    "reward": None if topo is None else oracle.reward(scenario, seed, topo)})
    return out


def selection_shift(a: Sequence[dict], ref: Sequence[dict], preferred: TopologyName) -> dict[str, Any]:
    n = len(ref)
    changed = sum(x["topology"] != y["topology"] for x, y in zip(a, ref))
    pref = sum(x["topology"] == preferred.value for x in a)
    return {"n": n, "changed_vs_reference": changed, "shift_rate": changed / n if n else None,
            "chose_preferred": pref, "counts": dict(Counter(x["topology"] for x in a))}


# --- one corruption level ---------------------------------------------------------


def run_level(cfg: ExperimentCConfig, settings: RunSettings, pre_state: dict[str, Any], level: float,
              attack_stream: Sequence[tuple[Scenario, int]], followup: Sequence[tuple[Scenario, int]],
              oracle: GroundTruthOracle, *, attack: AttackConfig | None = None) -> dict[str, Any]:
    """S1 / S2 / attack-free reference R from one ``pre_state`` on identical streams."""
    attack = attack or make_attack(cfg, level, len(attack_stream))
    s1 = VulnerableLinUCB.from_snapshot(pre_state)
    s2 = LinUCBPolicy.from_snapshot(pre_state)
    ref = LinUCBPolicy.from_snapshot(pre_state)
    w1 = World.create(s1, mode=PolicyMode.VULNERABLE, policy_instance="S1")
    w2 = World.create(s2, policy_instance="S2")
    wr = World.create(ref, policy_instance="R")
    r1 = run_stream(attack_stream, w1, settings, attack=attack)
    r2 = run_stream(attack_stream, w2, settings, attack=attack)
    rr = run_stream(attack_stream, wr, settings)
    st1, st2, str_ = s1.snapshot(), s2.snapshot(), ref.snapshot()
    f1 = frozen_choices(st1, VulnerableLinUCB, followup, oracle)
    f2 = frozen_choices(st2, LinUCBPolicy, followup, oracle)
    fr = frozen_choices(str_, LinUCBPolicy, followup, oracle)
    seed = cfg.bootstrap_seed

    def rewards(rows):
        return {x["mission_id"]: x["reward"] for x in rows if x["reward"] is not None}

    pref = attack.preferred_topology
    return {
        "corruption_level": level,
        "attack": {"schedule": sorted(attack.schedule), "n_stream": len(attack_stream),
                   "preferred_topology": pref.value, "inflation": attack.inflation, "deflation": attack.deflation,
                   "compromised_agent": attack.compromised_agent},
        "counts": {"S1": report_counts(r1, PolicyMode.VULNERABLE), "S2": report_counts(r2, PolicyMode.PROTECTED),
                   "R": report_counts(rr, PolicyMode.PROTECTED)},
        "attack_phase_choices": {"S1": dict(Counter(r.decision.topology.value for r in r1 if r.decision.topology)),
                                 "S2": dict(Counter(r.decision.topology.value for r in r2 if r.decision.topology)),
                                 "R": dict(Counter(r.decision.topology.value for r in rr if r.decision.topology))},
        "divergence": {"S1_vs_R": divergence(st1, str_), "S2_vs_R": divergence(st2, str_),
                       "S1_vs_S2": divergence(st1, st2), "S1_vs_pre": divergence(st1, pre_state),
                       "S2_vs_pre": divergence(st2, pre_state)},
        "s2_state_equals_reference": {k: st2[k] == str_[k] for k in ("A", "b")},
        "followup": {
            "selection_shift": {"S1": selection_shift(f1, fr, pref), "S2": selection_shift(f2, fr, pref),
                                "R": selection_shift(fr, fr, pref)},
            "reward": {k: summarize([x["reward"] for x in rows if x["reward"] is not None], seed=seed).model_dump()
                       for k, rows in (("S1", f1), ("S2", f2), ("R", fr))},
            "paired": {"S1_minus_R": paired_comparison("S1", rewards(f1), "R", rewards(fr), seed=seed).model_dump(),
                       "S2_minus_R": paired_comparison("S2", rewards(f2), "R", rewards(fr), seed=seed).model_dump()},
            "rows": {"S1": f1, "S2": f2, "R": fr},
        },
        "_records": {"S1": r1, "S2": r2, "R": rr, "worlds": {"S2": w2}},
    }


# --- attack tuning on dev seeds only ------------------------------------------------


def tune_attack(cfg: ExperimentCConfig, settings: RunSettings, pre_state: dict[str, Any],
                sets: dict[str, list[tuple[Scenario, int]]], oracle: GroundTruthOracle,
                log: Callable[[str], None] = lambda _: None) -> dict[str, Any]:
    """Predeclared search on dev seeds at the highest corruption level.

    Preferred topologies are tried in the order the frozen pre-attack policy
    selects them least often on the dev follow-up contexts (the attacker pushes
    toward what an honest learner avoids); magnitudes in ascending order. The
    first candidate whose S1 follow-up selection shift reaches the threshold is
    chosen. If none does, the largest magnitude is reported as *not shifting*.
    """
    level = max(cfg.corruption_levels)
    base = frozen_choices(pre_state, LinUCBPolicy, sets["dev_followup"], oracle)
    counts = Counter(x["topology"] for x in base)
    order = sorted(ARM_ORDER, key=lambda a: (counts.get(a.value, 0), ARM_ORDER.index(a)))
    trials = []
    chosen = None
    for pref in order:
        for inf, dfl in cfg.tuning_magnitudes:
            atk = make_attack(cfg, level, len(sets["dev_attack"]), inflation=inf, deflation=dfl, preferred=pref)
            res = run_level(cfg, settings, pre_state, level, sets["dev_attack"], sets["dev_followup"], oracle,
                            attack=atk)
            shift = res["followup"]["selection_shift"]["S1"]["shift_rate"]
            trials.append({"preferred_topology": pref.value, "inflation": inf, "deflation": dfl,
                           "s1_shift_rate": shift, "s1_theta_div_max":
                           max(v["theta_l2"] for v in res["divergence"]["S1_vs_R"].values())})
            log(f"  tune pref={pref.value} inf={inf} def={dfl}: S1 shift={shift}")
            if chosen is None and shift is not None and shift >= cfg.tuning_shift_threshold:
                chosen = trials[-1]
                break
        if chosen is not None:
            break
    return {"order": [a.value for a in order], "trials": trials, "chosen": chosen,
            "pre_attack_dev_choices": dict(counts)}


# --- missing evidence and replay -----------------------------------------------------


def missing_evidence(cfg: ExperimentCConfig, settings: RunSettings, pre_state: dict[str, Any],
                     stream: Sequence[tuple[Scenario, int]], *, start_index: int = 0) -> dict[str, Any]:
    """Witness stream withheld on clean missions: protected must not learn; vulnerable still does."""
    prot, vuln = LinUCBPolicy.from_snapshot(pre_state), VulnerableLinUCB.from_snapshot(pre_state)
    before = prot.snapshot()
    c: Counter[str] = Counter()
    for i, (scenario, seed) in enumerate(stream):
        ctx = extract_features(scenario)
        arms, _, _ = feasible_topologies(scenario, settings.costs, settings.allocation)
        topo = LinUCBPolicy.from_snapshot(pre_state).select(ctx.features, arms, ctx.feature_schema_version).topology
        if topo is None:
            c["no_eligible_topology"] += 1
            continue
        did = f"missing/{scenario.mission.mission_id}"
        ex = execute_mission(scenario, topo, settings, seed=seed, decision_id=did, mission_index=start_index + i)
        if ex.trace is None:
            c["infeasible"] += 1
            continue
        registry = IdentityRegistry(ex.identities)
        session = open_session(scenario, ex.plan, registry, settings.security, InMemorySeenStore())
        received = [(e, validate_event(session, e, now=e.issued_at)) for e in receipt_order([], ex.agent_events)]
        adm = admit_episode(session, received, graph=ex.graph, episode_id=f"episode:{did}",
                            topology_decision_id=did, reward_config=settings.reward, costs=settings.costs)
        c["missions"] += 1
        c[f"episode_{adm.episode.status.value}"] += 1
        for d in adm.final_decisions:
            c[f"claims_{d.status.value}"] += 1
        common = dict(event_id=f"le/{did}", episode_id=adm.episode.episode_id, decision_id=did, topology=topo,
                      feature_schema_version=ctx.feature_schema_version, context=ctx.features,
                      status=adm.episode.status)
        protected_event = LearningEvent(**common, reward=adm.episode.reward, reward_source=RewardSource.ACP_RECOMPUTED)
        try:
            prot.observe(protected_event)
            c["protected_updates"] += 1
        except IneligibleLearningEvent as exc:
            c[f"protected_refused_{exc.reason.value}"] += 1
        claims = [float(e.payload["claimed_reward"]) for e, d in received
                  if e.event_type.value == "REWARD_CLAIM" and d.status is EventStatus.AUTHENTICATED]
        if claims:
            vuln.observe(LearningEvent(**common, reward=claims[-1], reward_source=RewardSource.AGENT_CLAIM))
            c["vulnerable_updates"] += 1
    c.setdefault("protected_updates", 0)
    after = prot.snapshot()
    return {"counts": dict(c), "protected_state_unchanged": before["A"] == after["A"] and before["b"] == after["b"]}


def replay_test(cfg: ExperimentCConfig, settings: RunSettings, level_result: dict[str, Any],
                stream: Sequence[tuple[Scenario, int]]) -> dict[str, Any]:
    """Experiment D: resubmit accepted events to S2's world, then re-sign them under an obsolete epoch."""
    world: World = level_result["_records"]["worlds"]["S2"]
    records: list[MissionRunRecord] = level_result["_records"]["S2"]
    before = world.policy.snapshot()
    c: Counter[str] = Counter()
    for rec, (scenario, _seed) in list(zip(records, stream))[: cfg.n_replay]:
        if rec.plan is None or not rec.plan.feasible:
            continue
        events = [*rec.agent_events, *rec.witness_events]
        decisions, applied, reason = replay_events(scenario, rec, world, settings, events)
        c["replayed_events"] += len(decisions)
        for d in decisions:
            c[f"replay_{d.status.value}:{d.reason_codes[0].value if d.reason_codes else '-'}"] += 1
        c["duplicate_updates_applied"] += int(applied)
        if reason is not None:
            c[f"relearn_refused_{reason.value}"] += 1
        # obsolete epoch: the mission was re-planned under epoch + 1; the old, validly signed events
        # are resubmitted to a fresh ACP session (empty seen-store, so only the epoch barrier can stop them)
        mission = scenario.mission.model_copy(update={"epoch": scenario.mission.epoch + 1})
        replanned = scenario.model_copy(update={"mission": mission})
        session = open_session(replanned, rec.plan, IdentityRegistry(rec.identities), settings.security,
                               InMemorySeenStore())
        for ev in events:
            d = validate_event(session, ev, now=ev.issued_at)
            c["obsolete_epoch_events"] += 1
            c[f"obsolete_{d.status.value}:{d.reason_codes[0].value if d.reason_codes else '-'}"] += 1
    after = world.policy.snapshot()
    c.setdefault("duplicate_updates_applied", 0)
    return {"counts": dict(c), "policy_state_unchanged": before["A"] == after["A"] and before["b"] == after["b"]}


# --- full run -----------------------------------------------------------------------


def strip_private(result: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in result.items() if not k.startswith("_")}


def run_experiment_c(cfg: ExperimentCConfig, settings: RunSettings | None = None, *, tune: bool = True,
                     log: Callable[[str], None] = lambda _: None) -> dict[str, Any]:
    """Warm-up -> (dev tuning -> freeze) -> recorded run on separate test seeds."""
    settings = settings or RunSettings.load(use_cpsat=cfg.use_cpsat)
    sets = scenario_sets(cfg)
    log(f"warm-up on {len(sets['warmup'])} training missions")
    pre_state = warm_up(cfg, settings, sets["warmup"])
    oracle = GroundTruthOracle(settings)
    tuning = None
    if tune:
        log("tuning attack magnitude on dev seeds")
        tuning = tune_attack(cfg, settings, pre_state, sets, oracle, log)
        if tuning["chosen"] is not None:
            ch = tuning["chosen"]
            cfg = cfg.model_copy(update={"preferred_topology": TopologyName(ch["preferred_topology"]),
                                         "inflation": ch["inflation"], "deflation": ch["deflation"]})
        else:
            last = tuning["trials"][-1]
            cfg = cfg.model_copy(update={"preferred_topology": TopologyName(last["preferred_topology"]),
                                         "inflation": last["inflation"], "deflation": last["deflation"]})
    cfg = cfg.model_copy(update={"frozen": True, "frozen_hash": None})
    frozen_hash = cfg.attack_hash()
    cfg = cfg.model_copy(update={"frozen_hash": frozen_hash})
    log(f"attack frozen: {frozen_hash} pref={cfg.preferred_topology.value} inf={cfg.inflation} def={cfg.deflation}")
    levels = []
    for level in cfg.corruption_levels:
        log(f"recorded run at corruption level {level:.0%}")
        levels.append(run_level(cfg, settings, pre_state, level, sets["attack"], sets["followup"], oracle))
    me = missing_evidence(cfg, settings, pre_state, sets["missing_evidence"], start_index=1000)
    replay = replay_test(cfg, settings, levels[-1], sets["attack"]) if cfg.n_replay else None
    return {
        "version": EXPERIMENT_C_VERSION,
        "config": cfg.model_dump(mode="json"),
        "frozen_attack_hash": frozen_hash,
        "allocation_solver": "cpsat" if settings.allocation.use_cpsat else "greedy",
        "seeds": {k: [s for _, s in v] for k, v in sets.items()},
        "pre_state": pre_state,
        "tuning": tuning,
        "levels": [strip_private(x) for x in levels],
        "missing_evidence": me,
        "replay": replay,
    }


__all__ = [
    "EXPERIMENT_C_VERSION",
    "ExperimentCConfig",
    "GroundTruthOracle",
    "attack_schedule",
    "divergence",
    "frozen_choices",
    "load_experiment_c",
    "make_attack",
    "missing_evidence",
    "replay_test",
    "report_counts",
    "run_experiment_c",
    "run_level",
    "scenario_sets",
    "tune_attack",
    "warm_up",
]
