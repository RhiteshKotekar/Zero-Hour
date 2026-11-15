# Validator Handoff

## Project identity

- **Repository:** `RhiteshKotekar/Zero-Hour` (SAMG).
- **Branch / commit:** `main` at `f2a03e6919de9b9edc10c161c07a54129affc0f5` (`temp WIP`).
- **Validation environment:** Linux 7.3.1-1-cachyos x86_64, Python 3.14.8; cryptography 50.0.2, networkx 3.7, numpy 2.5.4, OR-Tools 9.15.6755, pydantic 2.14.3, Streamlit 1.67.0.
- **Working tree:** preserve the pre-existing user modification to `Temp_TASK.md`. The only validator edits are this file and `docs/VALIDATION_LOG.md`; `.venv` and `artifacts/` are ignored.

## Role and ownership

V independently validates implementation, artifacts, numerical claims, experiments, dashboard behaviour, and demo readiness. V may edit validation/results/docs and contract fixture data; the JSON issue also authorized targeted edits to the runner, dashboard data/view, and associated tests. Do **not** rewrite developer-owned domain, topology, allocation, simulation, assurance, witness, learning, persistence, orchestration, or core evaluation modules. Report their defects to the owner instead.

## Current status

Completed: environment/install, full suite, contract/integration/security tests, JSON artifact contract, frozen A/B rerun and repeatability check, AppTest dashboard acceptance, numerical spot checks, CLI demo rehearsal, and Experiment C rerun.

Current phase: documentation/handoff complete. Remaining work is owner follow-up, not an unverified JSON/dashboard task.

## Immediate dashboard JSON fix

**Original problem / root cause:** `scripts/run_experiment_a.py` wrote a human-readable `summary_json(result)` to `experiment_a.json`; the Adaptive Evaluation Lab attempted to deserialize that summary as a complete `ExperimentResult`. The summary lacks `training_rewards` and `records`, which are needed for the learning curve and held-out rows.

**Implementation in predecessor commit `f2a03e6`:**

- `scripts/run_experiment_a.py` writes complete `ExperimentResult.model_dump_json()` to `experiment_a.json` and a separate `experiment_a_summary.json`.
- `src/samg/dashboard/data.py` identifies missing, malformed, legacy-summary-only, and incompatible artifacts and raises an actionable `ExperimentLoadError`.
- `src/samg/dashboard/view_eval.py` catches that specific error instead of crashing.
- `tests/unit/dashboard/test_experiment_json.py` covers round trip, dashboard load, learning curves, comparison rows, missing/malformed/legacy/incompatible JSON, and summary validity.

**Acceptance evidence:** a real frozen run wrote a 1.1 MB full JSON, a 16 KB summary and CSV. `load_experiment_result()` loaded 960 records, six policies, three comparisons and five 120-value training series. Streamlit `AppTest` selected `experiment_a.json` and rendered four dataframes plus a Plotly learning curve with no exception/error. Focused JSON/dashboard tests: **25 passed**. Full suite: **337 passed**.

**Compatibility:** a legacy summary at the full-artifact path is intentionally rejected with instructions to rerun. No migration is attempted because summaries cannot reconstruct records or learning curves.

## Completed validation tasks

| ID | Command / calculation | Actual result | Status / evidence |
| --- | --- | --- | --- |
| V-JSON-01 | Focused dashboard tests | `25 passed in 2.70s` | PASS; `VALIDATION_LOG.md` continuation record |
| V-JSON-02 | Full test suite | `337 passed in 18.86s` | PASS |
| V-JSON-03 | `scripts/run_experiment_a.py` twice | Full artifacts are SHA-256 identical: `6df9ade8…3b9c` | PASS; summary differs only in recorded runtime |
| V-UI-01 | Streamlit `AppTest` | Aggregate lab loaded the full artifact; Mission Control live run and comparison, Security attack run, and reset controls all completed with no error | PASS; automated UI acceptance (no manual browser used) |
| V-MATH-01 | Context / handoff / reward / LinUCB calculations | `d=.25`, 2-hop cost `2.0`, normaliser `24.75`, rewards `1/0/.825`, θ `[.184,.046,.176,.096,.184]` | PASS |
| V-MATH-02 | Fixed judge allocation handoff oracle | H=`8.0`, F=`9.5`, D=`6.5` | PASS |
| V-DEMO-01 | Standard/greedy demo x2; protected runs seeds 1–3 x2 | All six pairwise outputs byte-identical; no host-clock text in demo output | PASS |
| V-SEC-01 | Assurance/persistence tests | `37 passed in 0.99s` | PASS; actual assertions reviewed for signature/role/freshness/state/append-only/restart/dedupe |
| V-SEC-02 | `scripts/run_experiment_c.py --out artifacts/validation/experiment_c --doc /tmp/...` | S2 admitted `0/6`, `0/12`; FRR `0/1609`; 15/15 no-evidence episodes provisional; replay `211` duplicates, 0 updates | PASS |
| V-FIXTURE-01 | Runtime `judge_scenario()` | agents A0–A5, tasks T1–T8, seven dependency edges | PASS. Contract fixture `01_reachable_mission.json` is intentionally a separate 2-agent/2-task fixture. |
| V-DECISION-01 | D009–D018 audit | All entries exist and agree with `THREE_PERSON_PLAN.md`; D020/D030–D037 also present | PASS |

## Failed checks

### VAL-001 — Historical A/B result not reproduced across environments

- **Responsible owner:** Dev A (runner/reproducibility/result documentation).
- **Reproduction:** `.venv/bin/python scripts/run_experiment_a.py`; config hash remains `8b98c35a16a6d069`.
- **Expected:** the frozen hash should identify reproducible published A/B values, or the documentation must state all versioned inputs needed for reproduction.
- **Actual:** fresh P3−P1 = `−0.005894` (95% CI `[−0.009153, −0.003071]`, n=54) vs historical `−0.00130` (`[−0.00332, +0.00046]`); P3−P2 = `+0.001776` (`[+0.000714, +0.002956]`, n=60) vs `+0.00629` (`[+0.00377, +0.00898]`). Two fresh runs are byte-identical, so this is not current-run randomness. Historical evidence says Python 3.12; this pass used Python 3.14 / newer unpinned OR-Tools. The hash excludes dependency versions.
- **Relevant invariant:** reproducibility/config provenance (no numbered brief invariant is cited in the repository).
- **Action:** do not overwrite `docs/RESULTS.md` or alter frozen seeds/config. Dev A should pin/record the validated runtime or amend the reproduction claim after an owner-approved rerun.

### VAL-002 — Exact INV-01…INV-09 wording unavailable

The frozen brief §8.9 is external to this repository. `docs/AI_CONTEXT.md` forbids inventing its exact wording. INV-05 and INV-08 have explicit enforcement and proving tests; the other numbered rows cannot be truthfully mapped until the brief (or an approved transcription) is supplied. This is a documentation input dependency, not evidence of an implementation failure.

## Experimental results

- **Experiment A/B:** fresh run ID is `artifacts/experiments/experiment_a.json`; frozen config hash `8b98c35a16a6d069`; results are recorded in `VALIDATION_LOG.md` and differ from historical documentation as VAL-001.
- **Experiment C:** isolated validation artifact `artifacts/validation/experiment_c/experiment_c.json`; attack hash `173ba5ea83c04bea`. At 40% corruption, S1 admits 12/12 false reports and shifts 26/30 later choices; S2 admits 0/12, remains byte-identical to clean reference, and has zero false rejections under the faithful-witness simulation. The evidence-gate state-protection claim is supported; utility harm is not supported by the reported CI.
- **Claims:** do not claim P3 beats best-fixed P1. The security claim is supported only under the documented trusted-witness/noiseless-evidence assumptions.

## Files changed

- `docs/VALIDATOR_HANDOFF.md` — created/updated by V.
- `docs/VALIDATION_LOG.md` — validation evidence added by V.
- `Temp_TASK.md` — pre-existing user edit; untouched by V.

## Next action

1. Give Dev A the VAL-001 reproduction data; decide whether to pin the published environment or re-run results under the documented historical environment.
2. Supply brief §8.9 (or an approved invariant transcription) so V can complete the INV-01…INV-09 trace table without inventing requirements.
3. A manual browser check is optional: automated AppTest acceptance has exercised all three tabs, live mission/comparison, live attack, saved aggregate, and reset controls. Run `streamlit run src/samg/dashboard/app.py` only if visual styling needs sign-off.

## Instructions for Codex

Read `CLAUDE.md`, `docs/THREE_PERSON_PLAN.md`, this file and `docs/VALIDATION_LOG.md` before new work. Do not redo the JSON fix or expensive experiments unless testing a changed environment/code. Preserve `Temp_TASK.md`; do not commit/push without user authorization. Treat `experiment_a.json` as the only dashboard-loadable full artifact; `experiment_a_summary.json` is display/export-only. Never change frozen configs/seeds to improve results, and report developer-owned defects rather than silently fixing them.
