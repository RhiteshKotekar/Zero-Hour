# Zero-Hour Control Center — Master Implementation Plan

Branch: `warehouse/control-center` (from `origin/main`). Decision record: `docs/DECISIONS.md` D038, D039.
This file is the hand-off document. **Any agent picking up work: read §0, §8 (status) and your phase in §7 only.**

---

## 0. Rules for every agent (read first)

1. **SAMG decides, the UI shows.** Topology, allocation, execution, witness/ACP verdicts, rewards and learning come
   from Python (`samg.*`). The frontend never chooses, scores, allocates or validates anything.
2. **No mock data.** Every value shown comes from the backend (live session) or from a recorded backend run
   (replay). If something genuinely has no backend source yet, it must be (a) listed in §9 *Mock register*,
   (b) labelled `MOCK` in the UI, (c) isolated in one module so it can be replaced by a real data stream.
3. **Stay in your lane.** Only edit the files/dirs your phase owns (§7). Don't refactor other code.
4. **Be token-efficient.** Read only the files your phase lists. Do not read the whole repo. Do not run the full
   pytest suite (≈40 s, unnecessary); run only what your phase's *Check* says. Full testing is Phase 4.
5. **Leave a trail.** When you finish (or stop), append to §8 *Status & hand-off log*: what is done, files touched,
   how you checked it, what is open. Tick the phase checkboxes. Files on disk are the checkpoint; do not commit or
   push unless the user asks.
6. Python: use `.venv/bin/python`. Node 24 / npm 11 are installed (no pnpm).

---

## 1. Goal

A Next.js **control center** that is the primary judge-facing UI: a live **3D warehouse digital twin** where
autonomous robots move through racks and aisles as SAMG plans and executes missions, plus a second **3D
communication view** of real-time agent-to-agent coordination. It must make obvious:

orders → SAMG mission → topology decision (and *why*: LinUCB scores + context) → CP-SAT allocation → robots
moving → congestion / failure → witness + ACP verification → secure reward → guarded learning → replanning.

It runs live (server-side simulation clock, user can start/pause/speed/inject failures and SAMG reacts) and as a
replay of recorded runs. The Streamlit dashboard stays as the secondary research UI.

## 2. Architecture

```
config/twin.yaml ─┐
                  ▼
samg.twin (Python)  ── orders → tasks → SAMG wave (feasible_topologies, policy.select, run_single_mission:
   │                    CP-SAT, simulator, witness, ACP, guarded update) → physical replay (A*, aisle locks)
   │                    → build_state()  ==  the state contract (§4)
   ▼
samg.twin.live.LiveSession   server clock, order arrivals, planning waves, time-anchored injections,
   │                         preview/commit of each wave, demo script, replay save/load
   ▼
samg.api (FastAPI)   REST commands + WebSocket stream  (http://localhost:8000)
   ▼
web/ (Next.js + React Three Fiber)   http://localhost:3000
   store (zustand) ← state snapshots + clock ticks;  derive.ts = pure functions of (state, t)
   3D warehouse · 3D comms · panels · controls
```

**Tick vs frame.** The server sends a full *state snapshot* only when the plan changes (new wave, injection,
commit) and a small *clock* message ~10×/s. The browser computes every robot position for its local time `t`
from the snapshot's segments (`derive.ts`) at 60 fps. No optimisation ever runs per frame.

**Two graphs, never merged.** Physical navigation graph = warehouse grid + A* + aisle locks (`samg.twin`).
Coordination graph = SAMG `CoordinationGraph` of the chosen topology (`state.waves[i].graph`).

## 3. What already exists (do not rebuild)

| Piece | Where | Notes |
| --- | --- | --- |
| SAMG pipeline | `samg.orchestration.run_single_mission`, `samg.allocation.feasible_topologies`, `samg.learning`, `samg.witness`, `samg.assurance` | unchanged contracts |
| Engine extensions | `samg.simulation.engine.run(..., task_delays_ms, agent_breakdowns)` | D038 |
| Warehouse twin backend | `src/samg/twin/` (`adapter.py`: `run_warehouse`, `execute`, `run_wave`, `build_state`, `compare_policies`, `trained_snapshot`; `environment.py`: `replay_wave`) | config `config/twin.yaml` |
| Teammate's Streamlit twin | `src/samg/warehouse/`, `src/samg/dashboard/view_warehouse*.py` | keep working; retain UI ideas (§6.6) |
| Real recorded run (contract sample) | `contract/state.judge_demo.json` | produced by `build_state(run_warehouse(preset(cfg,"judge_demo")))` |
| UI references to port | `contract/reference/control_room_light.html` (light control room: layout, tokens, all derive logic in JS), `contract/reference/comm_scene3d.html` (three.js comm scene) | port logic/styling, not copy-paste HTML |

## 4. State contract (`twin-state`)

`build_state()` output (see `contract/state.judge_demo.json`). Top-level keys:
`version, config_version, start_clock, spec, end_s, layout, inventory, robots, orders, tasks, waves, claims,
congestion, events, kpis` — plus additions made in Phase 1-A:

* `witness_events: [{t, task, from, to, wave}]` — every signed witness observation (for the comms view).
* `waves[i].allocation.handoffs[j]` gains `depart_s, arrive_s` (prerequisite end → + hops × hop delay).
* `waves[i].status: "planned" | "preview" | "committed"` (live only; replay = committed).
* `live: {session_id, mode: "live"|"replay", revision, t, playing, speed, rate, script: [...],
  injections: [{t, kind, target, effect, wave}], pending_orders: [...], planning: "idle"|"planning"|"running"}`.

Key semantics (unchanged from the existing twin): times are simulated seconds from `t=0` (`start_clock` gives
the wall-clock label). `robots[r].segments[]` are time-ordered `{t0,t1,kind: move|wait|work|idle|failed,
status, cell, path?, task?, aisle?, blockers?, b0,b1 (battery), o0,o1 (odometer)}`; `t1 = null` = forever.
A move segment traverses `path` cells uniformly between `t0` and `t1`. `tasks[].states[]` is the time-ordered
state history; `events[]` are pre-rendered, time-stamped, `level ∈ info|samg|move|warn|ok|bad|sec`.
**Everything must be revealed by time:** the UI shows only what has `t ≤ now`.

## 5. Backend design (Phase 1-A)

### 5.1 `samg.twin.live.LiveSession`
* **Spec**: scenario preset (`judge_demo`, `clean`, `rush`), policy (`adaptive|ucb1|P0-H|P0-F|P0-D`), seed,
  learner experience, CP-SAT on/off.
* **Order source** (`OrderSource` protocol, swappable for a real feed later): `ConfigOrderSource` (order book in
  `config/twin.yaml`, add optional `arrival: "HH:MM:SS"` per order, default start) and `GeneratedOrderSource`
  (seeded `generate_orders` at a configured interval — synthetic demand, flagged in §9).
* **Planning waves**: when no wave is running and arrived-but-unplanned tasks exist (new orders + tasks the
  witness did not verify), plan a wave with `run_wave(...)` from robots' current states and failed robots
  excluded (existing logic in `adapter.execute`, refactor into a step function; keep `run_warehouse` working).
* **Preview / commit**: a wave is first computed on a *scratch* world (policy clone, in-memory repo) =
  `preview`. When the clock passes the wave end, it is re-run on the *real* world with the same inputs
  (deterministic → identical trace; assert and log if not) = `committed`; only then does the learner update and
  the episode persist. This lets injections re-run the current wave without double-learning.
* **Time-anchored injections** (at current `t`, inside the running wave):
  * `robot_failure(robot)`: add engine param `agent_down_at_ms: {agent: ms}` (smallest extension, same file as
    D038: task executing at that time → FAILED at that time; later tasks → BLOCKED `AGENT_DOWN`); re-run preview.
  * `malicious_report(robot)`: robot's task executing at `t` (else next) becomes a forced abandon + `AttackConfig`
    claims (`schedule={idx}`, no sabotage schedule) → false completion + reward claims → ACP disputes.
  * `delayed_task(task|auto)`: `task_delays_ms[task] += delay`.
  * Re-run → new preview; prefix before `t` must be unchanged (check; log if not).
  * `comm_failure`, `aisle_blockage`, `inventory_unavailable`: environment changes for waves planned **after** `t`
    (state them as such in `live.injections[].effect`); if idle, trigger planning.
* **Clock loop** (asyncio, 10 Hz): advance `t` by `dt × speed × rate` when playing; process order arrivals,
  scripted injections (demo), wave commit, planning; bump `revision` and broadcast a snapshot when anything
  structural changed; broadcast `clock` every tick. `rate` default: 1 sim-second per real second × speed.
* **Demo script** (`scenarios.judge_demo.script` in YAML): timed injections, e.g. `{at: 95, kind: robot_failure,
  robot: auto:TRANSPORT}`, `{at: 40, kind: malicious_report, robot: auto:PICK}` — deterministic.
* **Replay store**: `artifacts/runs/<id>.json` (gitignored) = final state + spec + script; list/load.
* **Compare**: wrap `compare_policies` (cached).

### 5.2 `samg.api` (FastAPI, `python -m samg.api` → :8000, CORS for :3000)
| Method | Path | Body / result |
| --- | --- | --- |
| GET | `/api/health` | `{ok:true}` |
| GET | `/api/meta` | scenarios, policies, injection kinds (+ labels), robot ids, aisles, skus, layout |
| POST | `/api/session` | `{scenario, policy, seed, experience, use_cpsat}` → `{session_id, state}` (starts paused at t=0) |
| GET | `/api/session` | current state |
| POST | `/api/session/control` | `{action: play\|pause\|step\|reset\|speed, value?}` |
| POST | `/api/session/inject` | `{kind, robot?, aisle?, sku?, task?, delay_s?}` → `{accepted, at, effect}` |
| POST | `/api/compare` | `{seeds?, use_cpsat?}` → comparison JSON (shape of `compare_policies`) |
| GET/POST | `/api/runs`, `/api/runs/save`, `/api/runs/{id}` | replay list / save / load |
| WS | `/ws` | server → `{type:"hello",state,clock}`, `{type:"state",revision,state}`, `{type:"clock",t,playing,speed,revision}`, `{type:"notice",level,text}` |

One active live session per server (simple). Dependencies: add `fastapi`, `uvicorn[standard]` as optional extra
`api` in `pyproject.toml` (+ `requirements.txt`).

## 6. Frontend design (Phases 1-B, 2-C, 2-D)

### 6.1 Stack
`web/`: Next.js (current stable, App Router, TypeScript, React 19), Tailwind CSS, `three`,
`@react-three/fiber` (v9), `@react-three/drei`, `zustand`. Fonts via `next/font`: Inter + JetBrains Mono.
Env: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). No other UI kits.

### 6.2 Theme — **light industrial control room** (user requirement; not dark)
Port the tokens of `contract/reference/control_room_light.html` (`--bg #eef1f5`, white panels, thin `#e2e7ef`
borders, ink `#0b1220`, accent `#2563eb`, ok `#059669`, warn `#c2700a`, bad `#d92d2d`, sec `#7c3aed`,
samg `#0e7490`; role colours picking `#2563eb`, transport `#0d9488`, packing `#7c3aed`, dispatch `#ea580c`).
Dense, thin borders, small caps labels, mono numbers. No gradients, no cartoon, restrained motion.
3D scene: light concrete floor, soft directional light + shadows, white/grey racks with coloured bins.

### 6.3 Data layer (Phase 1-B)
* `web/lib/types.ts` — TS types for §4.
* `web/lib/derive.ts` — pure functions of `(state, t)`, ported from `control_room_light.html`: `robotAt`,
  `taskStateAt`, `assignmentAt`, `waveAt`, `orderStatusAt`, `kpisAt`, `congestionAt`, `visibleEvents`,
  `stageOf`, `claimsAt`, plus `handoffsInFlight`, `claimsInFlight` (comms view).
* `web/lib/store.ts` — zustand: `state`, `revision`, `mode ("live"|"replay")`, clock `{t, playing, speed,
  serverT, receivedAt}`, `localT()`, `selection {kind: robot|task|order|rack|aisle|claim|wave, id}`, UI toggles,
  `view: "ops"|"comms"`.
* Replay clock runs in the browser; live clock follows server `clock` messages (interpolate between ticks).
* `web/lib/api.ts`, `web/lib/ws.ts` (reconnecting) — Phase 2-D; Phase 1-B creates typed stubs.

### 6.4 Layout (single page `/`, plus `/compare`, `/replays`)
```
┌ Header: ZERO-HOUR · SECURE ADAPTIVE MISSION CONTROL │ ● LIVE/REPLAY · sim · scenario · topology · mission · policy · security ┐
├ Control bar: Session ▾ │ ▶ ❚❚ ⏭ ↻ │ 0.5 1 2 5× │ timeline (waves, markers) │ clock │ Inject ▾ │ ◉ Auto demo │ OPS | COMMS ┤
├ Pipeline strip: Warehouse → Orders → Mission → Topology → Allocation → Execution → Disruption → Witness → ACP → Reward → Learning ┤
├──────────── 3D view (ops or comms) ≈ 68% ─────────────┬──── right rail ──────────────────────┤
│ overlay: camera buttons, phase banner, toasts,      │ Mission status (counters, orders +   │
│ selection info card                                 │ step bars, order→task→robot lineage)  │
│                                                     │ Topology decision (graph from state, │
│                                                     │ LinUCB mean+bonus bars, context,     │
│                                                     │ eligibility reasons, wave history)   │
├──── KPI strip (10 KPIs) ───────────────────────────┴───────────────────────────────────────┤
├ Bottom tabs: Allocation · Security (5-step claim pipeline) · Events (filters) · Fleet · Provenance ┤
```

### 6.5 3D operations view (Phase 1-B)
Floor 30×20 with zone floor tints and labels (receiving, robot park, control/WMS, main aisles, storage, cons-
olidation, packing, staging, replenishment, dispatch); racks = frames + shelf levels + bins (instanced); narrow
aisles marked as single-lane; walls; pack stations (tables + arm), dock doors (striped), chargers, WMS tower;
consolidation points; SKU bins highlighted when an order needs them. Robots: low AMR body + lidar puck + status
light, role colour, tote when carrying, floor status ring (progress while working), label (id + status).
Movement interpolated along `segments` via `useFrame` refs (no React re-render per frame). Routes: remaining
path (dashed), future legs of the same task (faint), destination marker. Congestion: aisle highlight +
"AI-3 · 2 waiting · +12 s" label. Failure: red beacon + X. Witness ✓ ring; "CLAIM REJECTED" burst.
Optional overlay: SAMG coordination links between live robot positions. Camera: orbit/zoom/pan, `Top`, `3D`
(isometric), `Follow robot`, `Reset`, `Focus selection/congestion/failure`. Click robot/rack/aisle/task →
`selection`.

### 6.6 Panels to retain (Phase 2-C)
From the light control room (`control_room_light.html`, which the user likes): header chips, control bar,
pipeline strip, KPI strip, mission counters + orders with per-task step bars, topology panel (graph +
"LINUCB SCORE = MEAN + UNCERTAINTY BONUS" bars + context vector + "no explanation is generated" note +
ADAPTIVE DECISION chip), allocation table (live status, ETA, zone, ↺ reassigned-from highlight), 5-step
security pipeline (claim → signature → witness → ACP → learning, gated by time), event stream with filter
chips, fleet list (status/task/battery/odometer), comparison table (best mean only among eligible, ± std,
honesty note), provenance footer.
From the teammate's Streamlit twin (`src/samg/dashboard/view_warehouse.py` on main): **order lineage**
(order → tasks → robots), **backend provenance** panel, **phase-by-phase pipeline header**, protected-vs-
vulnerable comparison idea (Experiment C), the 3D look of `view_warehouse_3d.py`.

### 6.7 3D communication view (Phase 2-D) — toggle `OPS | COMMS`
Same clock. Nodes: WMS hub, robots (role colours; failed = grey/red), ACP (crystal), Witness (eye),
LinUCB learner. Edges: current wave's coordination graph (hub/cell/bridge/direct styles, from
`waves[i].graph`). Live traffic: handoff packets travelling the graph path hop by hop (`depart_s→arrive_s`),
signed claims robot→ACP turning green/red on verdict, witness observations witness→ACP, guarded update
ACP→learner at wave commit, topology switch animation when a new wave starts. Side legend + "messages in
flight" counter. Light theme. Port ideas from `contract/reference/comm_scene3d.html`, restyled.

### 6.8 Demo mode
`◉ Auto demo` (live): start session `judge_demo` (scripted injections, fixed seed) and show phase banners
anchored to real events (logic: `buildPhases` in `control_room_light.html`). Replay: same banners on a stored run.

## 7. Phases

Status boxes are mirrored in §8. Owners are agent roles.

### Phase 0 — Plan & port (orchestrator) ✅
Branch, port twin as `samg.twin`, D038/D039, contract sample + references, this plan.

### Phase 1-A — Live backend (owns `src/samg/twin/live.py`, `src/samg/twin/sources.py`, `src/samg/api/**`,
small edits in `src/samg/twin/adapter.py`, `src/samg/twin/scenarios.py`, `config/twin.yaml`,
`src/samg/simulation/engine.py` (agent_down_at_ms only), `src/samg/orchestration.py` (pass-through only),
`pyproject.toml`, `requirements.txt`, `tests/unit/twin/test_live.py`)
- [x] engine `agent_down_at_ms` + pass-through
- [x] state additions (§4): `witness_events`, handoff `depart_s/arrive_s`, `waves[].status`, `live`
- [x] `OrderSource` (config + generated), order `arrival`
- [x] `LiveSession`: planning waves, preview/commit, time-anchored injections, env injections, demo script
- [x] replay store, compare wrapper
- [x] FastAPI app + WS + `python -m samg.api`
- **Check:** `.venv/bin/python -m samg.api` starts; curl `POST /api/session` (judge_demo) → state; `control
  play`; after ~5 s `GET /api/session` shows `live.t>0`; one `inject robot_failure` returns accepted and the
  next state shows the failed robot. Add ≤3 focused tests in `tests/unit/twin/test_live.py` and run only them.

### Phase 1-B — Frontend foundation + 3D warehouse (owns `web/**` except files listed for 2-C/2-D)
- [x] scaffold `web/` (Next.js, TS, Tailwind, R3F, drei, zustand, fonts), theme tokens, `npm run dev`
- [x] `lib/types.ts`, `lib/derive.ts`, `lib/store.ts`, replay clock; copy `contract/state.judge_demo.json` to
      `web/public/replays/judge_demo.json` (it is a real recorded run; label UI `REPLAY · recorded SAMG run`)
- [x] **stub files** with final export names for 2-C/2-D (so they can work in parallel):
      `components/panels/*` (MissionPanel, TopologyPanel, AllocationTable, SecurityPipeline, EventStream,
      FleetList, KpiStrip, ProvenancePanel, PipelineStrip, Header, ControlBar), `components/comms/CommsView.tsx`,
      `components/live/{SessionDrawer,InjectMenu,DemoBanner}.tsx`, `lib/api.ts`, `lib/ws.ts`,
      `app/compare/page.tsx`, `app/replays/page.tsx`
- [x] `components/warehouse3d/**`: full 3D ops view (§6.5) + camera controls + selection
- [x] `app/page.tsx`: minimal shell rendering the 3D view in replay mode with play/pause (2-C replaces shell)
- **Check:** `cd web && npm run build` passes; `npm run dev` page shows the warehouse with moving robots from the
  replay (one headless screenshot is enough).

### Phase 2-C — Panels & page shell (owns `web/app/page.tsx`, `web/app/layout.tsx`, `web/components/panels/**`,
`web/components/shell/**`)
- [ ] full layout §6.4 with all panels §6.6, selection interactions (click panel rows ↔ 3D highlight), toasts
- **Check:** `npm run build`; screenshot of the page in replay at 2 times (≈60 s and end).

### Phase 2-D — Live wiring, comms 3D, demo, compare, replays (owns `web/lib/api.ts`, `web/lib/ws.ts`,
`web/lib/live.ts`, `web/components/live/**`, `web/components/comms/**`, `web/app/compare/**`,
`web/app/replays/**`)
- [ ] api + ws clients, live mode in store (via exported hook `useLiveConnection()`), SessionDrawer, InjectMenu,
      control actions → REST
- [ ] CommsView (§6.7)
- [ ] Auto demo + DemoBanner (§6.8)
- [ ] `/compare` (run + table), `/replays` (list/save/load)
- **Check:** `npm run build`; with backend running: start judge_demo, play, inject a failure, see it in 3D
  (one screenshot); comms view screenshot.

### Phase 3 — Integration & polish (single agent; may touch everything in `web/` + `scripts/` + README)
- [ ] `scripts/dev.sh` (starts API + web), README "Control center" section
- [ ] end-to-end judge demo run-through (live), fix wiring/visual issues, performance check (60 fps target)
- [ ] mock register (§9) final, honest labels
- **Check:** demo run-through with 3–4 screenshots at key moments.

### Phase 4 — Validation (only when the user asks)
Backend tests for live session, frontend smoke (build + Playwright optional), full pytest, cleanup.

## 8. Status & hand-off log

| Phase | Status |
| --- | --- |
| 0 Plan & port | ✅ done |
| 1-A Live backend | ✅ done |
| 1-B Frontend + 3D | ✅ done |
| 2-C Panels | ⬜ |
| 2-D Live/comms/demo | ⬜ |
| 3 Integration | ⬜ |
| 4 Validation | ⬜ (on request) |

Log (append newest last; date · phase · agent · summary · files · check · open issues):

* 2026-11-15 · P0 · orchestrator · branch `warehouse/control-center` from origin/main; ported the twin backend
  as `samg.twin` (+ `config/twin.yaml`, tests `tests/unit/twin` 24 pass); engine/orchestration D038 extensions;
  D039; contract sample `contract/state.judge_demo.json`; UI references in `contract/reference/`.
* 2026-11-15 · P1-A · backend agent · live backend done.
  **Files:** `src/samg/simulation/engine.py` (`agent_down_at_ms`), `src/samg/orchestration.py` (pass-through in
  `execute_mission`/`run_single_mission`), `src/samg/twin/adapter.py` (`WaveOverrides` + `run_wave(overrides=)`,
  `Wave.status`, `_mark_down`, build_state additions), `src/samg/twin/sources.py` (new), `src/samg/twin/live.py`
  (new), `src/samg/api/{__init__,__main__,app}.py` (new), `config/twin.yaml` (W004 `arrival: 09:40:45`,
  `judge_demo.script`, `rush` scenario, `live:` block), `pyproject.toml` (extra `api`), `requirements.txt`,
  `tests/unit/twin/test_live.py` (3 tests). fastapi 0.163 / uvicorn 0.54 installed in `.venv`.
  **Check:** `pytest tests/unit/twin` 27 pass (14 s); `build_state(run_warehouse(judge_demo))` is byte-identical to
  `contract/state.judge_demo.json` apart from the new keys; smoke: `python -m samg.api`, POST session judge_demo,
  play ×5, `live.t>0`, script fired malicious_report@20 (R03) + operator robot_failure R04 → accepted, next state has
  R04 `failed_at` + `failed` segment; WS hello/state/clock/notice received; runs save/list; reset; CORS preflight 200.
  Full judge_demo live run: 2 waves, wave 1 HIERARCHICAL with R03 false claims DISPUTED (2) and R05 down at 70 s,
  wave 2 replans 7 tasks + new order W004 without R05, 4/4 orders dispatched; every commit == preview.
  **Contract as implemented (frontend agents read this):**
  - State additions: `witness_events[] = {t, task, from, to, witness, wave}` (`from`/`to` are *task states*, the
    edge is witness→ACP); handoffs gain `depart_s, arrive_s` (`null` if the prerequisite never completed);
    `waves[i].status ∈ preview|committed` (`planned` is never emitted); `orders[i].arrival_s`;
    `spec.order_source ∈ config|generated`; `live = {session_id, mode, revision, t, playing, speed, rate,
    complete, script: [{at, kind, robot?/aisle?/sku?/task?/delay_s?, fired}], injections: [{t, kind, target,
    effect, wave (null for environment/idle), source: operator|script}], pending_orders: [order ids arrived but
    not yet in a wave], planning: idle|running}`. `state.orders` contains only *arrived* orders.
    In live mode the last wave is the running `preview` (its future is already in segments/states; reveal by t).
  - REST: `GET /api/health`; `GET /api/meta` → `{scenarios:[{id,label,seed,policy,order_source,script}],
    policies:[{id,label}], injections:[{kind,label,scope: wave|environment, needs:[...]}], robots:[{id,role,label,
    physical}], aisles:[...], skus:[{sku,name,stock}], layout, environment_injections}`;
    `POST /api/session` → `{session_id, state}` (paused, t=0; first adaptive session ≈12 s for learner warm-up,
    cached afterwards); `GET /api/session` → `{session_id, state}` or `{session_id:null, state:null}`;
    `POST /api/session/control {action, value?}` → `{session_id, clock}` (`step` = advance `value` sim-s,
    default 5; `speed` needs value>0; `reset` = new session with the same params, new session_id);
    `POST /api/session/inject` → `{accepted, at, kind, target, effect, wave, source}` (rejections are
    `accepted:false` with the reason in `effect`, HTTP 200; unknown kind → 400; no session → 409);
    `POST /api/compare {seeds?, use_cpsat?}` → `compare_policies` JSON (slow on first call, cached);
    `GET /api/runs` → `[meta]`; `POST /api/runs/save {name?}` → `meta = {id, saved_at, scenario, policy, seed, t,
    end_s, waves, complete}`; `GET /api/runs/{id}` → `{meta, spec, script, state}` with `state.live.mode="replay"`.
  - WS `/ws` (server→client only): `{type:"hello", state|null, clock:{t,playing,speed,revision}}`,
    `{type:"state", revision, state}`, `{type:"clock", t, playing, speed, revision}` (10 Hz),
    `{type:"notice", level: ok|warn|bad, text}`.
  **Semantics / open issues:** waves are sequential (an order arriving mid-wave waits for the wave end — W004
  arrives at 45 s and is planned at ≈285 s); a wave whose task set, environment and excluded robots are unchanged
  is not re-planned (no infinite replanning); `robot_failure` with no running wave = idle failure (excluded from
  later waves, `failed` segment added by the live layer); `malicious_report`/`delayed_task` need a running wave;
  one compromised robot per wave. The clock loop caps a tick at 0.25 real s, so a slow re-plan pauses rather than
  jumps the clock. Session auto-pauses with `live.complete=true` when nothing is left. `rush` uses
  `GeneratedOrderSource` only in live sessions (`run_warehouse(preset(cfg,"rush"))` still uses the config book).
* 2026-11-15 · P1-B · frontend agent · frontend foundation + 3D warehouse done.
  **Stack:** Next.js 16.4.6 (App Router, Turbopack, `cacheComponents` on — scaffold default), React 19.3, Tailwind 4,
  three 0.187, @react-three/fiber 9.8, drei 10.7, zustand 5.1; Inter + JetBrains Mono via `next/font`
  (`--font-inter`/`--font-jetbrains` → Tailwind `font-sans`/`font-mono`). NB `web/AGENTS.md`: Next 16 has breaking
  changes — check `web/node_modules/next/dist/docs/` before using unfamiliar APIs. Theme tokens (§6.2) are CSS vars in
  `app/globals.css` and Tailwind colours (`bg-bg bg-panel bg-panel2 border-line border-line2 text-ink text-ink2
  text-muted text-faint text-accent/ok/warn/bad/sec/samg` + `*-bg` variants, `pick/transport/pack/dispatch`), helper
  classes `.cap` (small-caps label), `.mono`, `.btn(.primary|.on)`, `.seg`, `.pulse`.
  **Files:** `web/{package.json,next.config.ts,app/{layout,page,globals.css},app/compare/page.tsx,app/replays/page.tsx}`,
  `web/lib/{types,derive,store,api,ws,live}.ts`, `web/components/warehouse3d/{WarehouseView,Scene,Floor,floorTexture,
  Racks,Structures,Robots,Routes,Overlays,CameraRig,InfoCard,InstancedBoxes,palette,labelPortal,index}.ts(x)`,
  stubs in `web/components/{panels,live,comms}/`, `web/public/replays/judge_demo.json` (copy of the contract sample).
  **Check:** `npm run build` passes (also `npx tsc --noEmit`, `npx eslint .` clean); `npm run dev` + headless Chrome
  screenshots at t=20/62/108 s show the warehouse, moving robots with dashed routes, AI-2 congestion badge, R06 FAILED
  beacon/X + burst, SKU highlights; browser console clean (only three's `THREE.Clock` deprecation from R3F).
  **APIs for Phase 2 (use these, don't re-derive):**
  - `lib/store.ts` → `useStore` (zustand) with `state, revision, mode ("live"|"replay"), source, clock {t, playing, speed,
    serverT, receivedAt}, selection {kind: robot|task|order|rack|aisle|claim|wave, id} | null, hover, toggles {routes,
    coord, labels, congestion, effects}, view ("ops"|"comms"), follow (robot id|null), camera {kind, nonce}`; actions
    `localT(), endT(), setState(state, {revision?, mode?, source?, resetClock?}), loadReplay(url, source?), play(),
    pause(), togglePlay(), setSpeed(n), seek(t), applyServerClock({t, playing, speed}) (live: call on every WS clock),
    commit(), select(sel|null), setHover(sel|null), toggle(key), setView(v), setFollow(id|null),
    cameraCommand("top"|"iso"|"reset"|"follow"|"focusSelection"|"focusCongestion"|"focusFailure")`. Hooks:
    `useClockDriver(hz=10)` (mount ONCE in the page shell; commits `localT()` into `clock.t`, auto-stops replay at
    end), `useSimT()` (committed t, re-renders ≈10 Hz — use in panels), `getLocalT()` (non-reactive, use in useFrame).
    Live mode: `setState(state, {mode:"live", revision})` on WS hello/state; `localT()` extrapolates with
    `speed × live.rate`.
  - `lib/derive.ts` (pure, `(state, …, t)`; per-state indices cached in a WeakMap): `robotAt(state,id,t)` →
    `{x,y,dx,dy,status,task,battery,odo,seg,idx,f}` (grid coords, cell-centre), `robotRoute`, `pathPos`,
    `taskStateAt(state,taskId,t)`, `assignmentAt(state,taskId,t)`, `waveAt(state,t)`, `orderStatusAt(state,orderId,t)`
    → `{label,tone: ok|warn|bad|ink|sec, sub}`, `kpisAt(state,t)` → `{ocr,ocrN,ful,lat,util,dist,cong,fails,viol,rew,
    rewW,topo}`, `congestionAt(state,t)` → `[{aisle,entries,waiting,remaining,label}]`, `visibleEvents(state,t)`,
    `stageOf(event)`, `STAGES`, `claimsAt(state,t)`, `failedRobotsAt`, `handoffsInFlight(state,t)` (uses
    `depart_s/arrive_s`, skips null), `claimsInFlight(state,t,window=1.5)`, `effectsAt(state,t)`,
    `buildPhases(state, hasCompare)` (§6.8 banners), `indexOf(state)` (task/robot maps, wms, wmsPos), formatting
    `clockAt(state,t)`, `fmtS`, `pct`, `topoLabel`, palettes `ROLE_COLOR`, `LEVEL_COLOR`, `STATUS_COLOR`,
    `TASK_STATUS_LABEL`.
  - 3D: `import WarehouseView from "@/components/warehouse3d/WarehouseView"` via `next/dynamic(..., {ssr:false})`;
    props `{className?, bare?}` (bare = no built-in overlay). It reads everything from the store; selection is
    `useStore.selection` both ways (panel row click → `select({kind:"robot",id})` highlights in 3D;
    `cameraCommand("focusSelection")` flies there).
  - Stubs (final export names, named + default): `components/panels/{MissionPanel,TopologyPanel,AllocationTable,
    SecurityPipeline,EventStream,FleetList,KpiStrip,ProvenancePanel,PipelineStrip,Header,ControlBar}.tsx` (props
    `{className?}`), `components/live/{SessionDrawer,InjectMenu,DemoBanner}.tsx`, `components/comms/CommsView.tsx`,
    `lib/api.ts` (`API_URL, getHealth, getMeta, createSession, getSession, control, inject, compare, listRuns,
    saveRun, loadRun` — typed per the 1-A contract, throw "not implemented"), `lib/ws.ts` (`WsMessage, connectWs(handlers,
    url?) → {close}`), `lib/live.ts` (`useLiveConnection(enabled)` — owned by 2-D), `app/{compare,replays}/page.tsx`.
  **Open issues:** `app/page.tsx` is a minimal shell (header + play/pause/speed/scrubber; URL params `?t=`, `?paused=1`,
  `?speed=`), Phase 2-C replaces it. drei `<Html>` labels must pass `portal={labelPortal}` (stable target; otherwise
  every label root remounts on load and React logs "synchronously unmount a root"). Headless-Chrome screenshots can
  show the canvas shorter than its container (ResizeObserver vs virtual time) — not seen as a layout bug. Witness
  rings come from `events` ("Witness verified …"); `witness_events` are not used by the ops view. 60 fps not measured
  on real hardware (swiftshader only); scene uses instancing (≈10 instanced meshes for racks/structures), one canvas
  floor texture, per-frame robot updates via refs only.

## 9. Mock register

Nothing may appear here without a UI `MOCK` label. Current entries:

| What | Where | Why | Replace with |
| --- | --- | --- | --- |
| *(none yet)* | | | |

Not mock, but simulated (state it in the provenance panel): robot motion/battery (twin physics model),
generated order stream in `rush` mode (seeded `generate_orders`), simulated clock.

## 10. Run (target)

```bash
.venv/bin/pip install -e ".[api]"          # once
.venv/bin/python -m samg.api                # http://localhost:8000
cd web && npm install && npm run dev        # http://localhost:3000
# or: scripts/dev.sh
```
