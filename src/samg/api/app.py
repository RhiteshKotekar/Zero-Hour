"""FastAPI app: REST commands + WebSocket stream for one live ``LiveSession`` per server.

WebSocket ``/ws`` (server -> client only):

* ``{"type": "hello", "state": <state|null>, "clock": {t, playing, speed, revision}}`` on connect;
* ``{"type": "state", "revision": n, "state": <state>}`` whenever the session revision changes;
* ``{"type": "clock", "t", "playing", "speed", "revision"}`` every tick (10 Hz);
* ``{"type": "notice", "level", "text"}`` for injections, warnings and completion.

The server owns the simulation clock; the browser only interpolates. Nothing here decides
anything: every value comes from ``samg.twin.live`` (and through it from SAMG).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from samg.twin.layout import load_config
from samg.twin.live import ENV_INJECTIONS, WAVE_INJECTIONS, LiveSession, compare, list_runs, load_run, save_run
from samg.twin.scenarios import INJECTION_KINDS, POLICY_KINDS

log = logging.getLogger(__name__)
CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


class SessionRequest(BaseModel):
    scenario: str = "judge_demo"
    policy: str | None = None
    seed: int | None = None
    experience: int | None = None
    use_cpsat: bool = True


class ControlRequest(BaseModel):
    action: str
    value: float | None = None


class InjectRequest(BaseModel):
    kind: str
    robot: str | None = None
    aisle: str | None = None
    sku: str | None = None
    task: str | None = None
    delay_s: float | None = None


class CompareRequest(BaseModel):
    seeds: list[int] | None = None
    use_cpsat: bool = True


class SaveRequest(BaseModel):
    name: str | None = None


class Hub:
    """The single live session and the connected WebSocket clients."""

    def __init__(self) -> None:
        self.session: LiveSession | None = None
        self.clients: set[WebSocket] = set()
        self.sent_revision: tuple[str, int] | None = None

    def clock(self) -> dict[str, Any]:
        s = self.session
        return s.clock() if s else {"t": 0.0, "playing": False, "speed": 1.0, "revision": 0}

    async def broadcast(self, msg: dict[str, Any]) -> None:
        if not self.clients:
            return
        text = json.dumps(msg)
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:  # noqa: BLE001 - a dropped client must not stop the loop
                self.clients.discard(ws)

    async def publish(self) -> None:
        """Send notices, a state snapshot if the revision changed, then the clock."""
        s = self.session
        if s is not None:
            for n in s.drain_notices():
                await self.broadcast({"type": "notice", **n})
            key = (s.session_id, s.revision)
            if key != self.sent_revision:
                self.sent_revision = key
                if self.clients:
                    state = await asyncio.to_thread(s.state)
                    await self.broadcast({"type": "state", "revision": state["live"]["revision"], "state": state})
        await self.broadcast({"type": "clock", **self.clock()})


def create_app() -> FastAPI:
    """Build the app; its lifespan runs the 10 Hz clock loop."""
    cfg = load_config()
    hub = Hub()
    tick = 1.0 / float(cfg.get("live", {}).get("tick_hz", 10))

    async def clock_loop() -> None:
        last = time.monotonic()
        while True:
            await asyncio.sleep(tick)
            now = time.monotonic()
            dt, last = now - last, now
            try:
                s = hub.session
                if s is not None and s.playing:
                    await asyncio.to_thread(s.advance_real, dt)
                await hub.publish()
            except Exception:  # noqa: BLE001 - keep the clock alive, report the error
                log.exception("clock loop error")
                await hub.broadcast({"type": "notice", "level": "bad", "text": "server error in clock loop (logged)"})

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(clock_loop())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="Zero-Hour control center API", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
    app.state.hub = hub

    def session() -> LiveSession:
        if hub.session is None:
            raise HTTPException(409, "no live session; POST /api/session first")
        return hub.session

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        from samg.twin.adapter import WarehouseEnv

        env = WarehouseEnv(cfg)
        return {
            "scenarios": [{"id": k, "label": v.get("label", k), "seed": v.get("seed"), "policy": v.get("policy"),
                           "order_source": (v.get("orders") or {}).get("source", "config"),
                           "script": v.get("script", [])} for k, v in cfg["scenarios"].items()],
            "policies": [{"id": k, "label": v} for k, v in POLICY_KINDS.items()],
            "injections": [{"kind": k, "label": v, "scope": "wave" if k in WAVE_INJECTIONS else "environment",
                            "needs": {"robot_failure": ["robot"], "malicious_report": ["robot"],
                                      "delayed_task": ["task?", "delay_s?"], "aisle_blockage": ["aisle"],
                                      "inventory_unavailable": ["sku"], "comm_failure": []}[k]}
                           for k, v in INJECTION_KINDS.items()],
            "robots": [{"id": r.robot_id, "role": r.role, "label": r.label, "physical": r.physical}
                       for r in env.robots],
            "aisles": [a.aisle_id for a in env.layout.aisles],
            "skus": [{"sku": s.sku, "name": s.name, "stock": s.stock} for s in env.inventory.all()],
            "layout": env.layout.to_json(),
            "environment_injections": list(ENV_INJECTIONS),
        }

    @app.post("/api/session")
    async def create_session(req: SessionRequest) -> dict[str, Any]:
        try:
            s = await asyncio.to_thread(LiveSession, req.scenario, req.policy, req.seed, req.experience,
                                        req.use_cpsat, cfg)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        hub.session = s
        return {"session_id": s.session_id, "state": await asyncio.to_thread(s.state)}

    @app.get("/api/session")
    async def get_session() -> dict[str, Any]:
        s = hub.session
        if s is None:
            return {"session_id": None, "state": None}
        return {"session_id": s.session_id, "state": await asyncio.to_thread(s.state)}

    @app.post("/api/session/control")
    async def control(req: ControlRequest) -> dict[str, Any]:
        s = session()
        if req.action == "reset":
            p = s.params
            hub.session = await asyncio.to_thread(LiveSession, p["scenario"], p["policy"], p["seed"],
                                                  p["experience"], p["use_cpsat"], cfg, p["script"])
            return {"session_id": hub.session.session_id, "clock": hub.session.clock()}
        try:
            clock = await asyncio.to_thread(s.control, req.action, req.value)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"session_id": s.session_id, "clock": clock}

    @app.post("/api/session/inject")
    async def inject(req: InjectRequest) -> dict[str, Any]:
        s = session()
        try:
            return await asyncio.to_thread(lambda: s.inject(req.kind, robot=req.robot, aisle=req.aisle, sku=req.sku,
                                                            task=req.task, delay_s=req.delay_s))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/compare")
    async def run_compare(req: CompareRequest) -> dict[str, Any]:
        return await asyncio.to_thread(compare, tuple(req.seeds) if req.seeds else None, req.use_cpsat)

    @app.get("/api/runs")
    def runs() -> list[dict[str, Any]]:
        return list_runs()

    @app.post("/api/runs/save")
    async def save(req: SaveRequest) -> dict[str, Any]:
        return await asyncio.to_thread(save_run, session(), req.name)

    @app.get("/api/runs/{run_id}")
    def load(run_id: str) -> dict[str, Any]:
        try:
            return load_run(run_id)
        except KeyError as e:
            raise HTTPException(404, f"no stored run {run_id}") from e

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        s = hub.session
        state = await asyncio.to_thread(s.state) if s else None
        await socket.send_text(json.dumps({"type": "hello", "state": state, "clock": hub.clock()}))
        hub.clients.add(socket)
        try:
            while True:
                await socket.receive_text()   # client messages are ignored; commands go through REST
        except WebSocketDisconnect:
            pass
        finally:
            hub.clients.discard(socket)

    return app


app = create_app()
