"""3D Warehouse Digital Twin View for SAMG Mission Control.

Renders a live, interactive 3D WebGL warehouse digital twin using Three.js and OrbitControls.
Directly consumes SAMG simulation state, LinUCB topology choices, CP-SAT task allocation,
autonomous AMR physical execution, A* route waypoints, aisle congestion, and ACP witness security events.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
import streamlit as st

from samg.warehouse.agents import RobotStatus, WarehouseRobot
from samg.warehouse.layout import CellType, WarehouseLayout
from samg.warehouse.orders import OrderStatus, WarehouseOrder
from samg.warehouse.state import WarehouseState


STATIC_DIR = Path(__file__).parent / "static"


def _load_static_js(filename: str, cdn_fallback: str) -> str:
    """Load vendored JavaScript or fallback to CDN."""
    file_path = STATIC_DIR / filename
    if file_path.exists():
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return f"/* Loaded via CDN fallback */"


def serialize_warehouse_scene(
    state: WarehouseState,
    steps: list[WarehouseState] | None = None,
    current_step_idx: int = 0,
    auto_play: bool = False,
) -> dict[str, Any]:
    """Serialize authentic SAMG warehouse state into 3D scene representation."""
    layout = state.layout
    steps = steps or [state]
    current_step_idx = max(0, min(current_step_idx, len(steps) - 1))

    # Rack structures
    racks_data = []
    for rack_id, rack in layout.racks.items():
        racks_data.append({
            "id": rack_id,
            "aisle": rack.aisle,
            "x_min": rack.x_min,
            "x_max": rack.x_max,
            "y_min": rack.y_min,
            "y_max": rack.y_max,
            "access_points": list(rack.access_points),
        })

    # Stations & zones
    stations_data = {}
    for st_id, (sx, sy) in layout.stations.items():
        stations_data[st_id] = {"x": sx, "y": sy}

    # Extract all frames for continuous timeline playback
    timeline_frames = []
    for step in steps:
        robots_frame = {}
        for r_id, robot in step.robots.items():
            # Calculate heading angle in radians from route
            heading = 0.0
            if robot.route and len(robot.route) > 1:
                cur_x, cur_y = robot.current_position
                # Look ahead to next waypoint
                target_pt = robot.route[min(1, len(robot.route) - 1)]
                dx = target_pt[0] - cur_x
                dy = target_pt[1] - cur_y
                heading = math.atan2(dx, dy)

            robots_frame[r_id] = {
                "id": r_id,
                "samg_agent_id": robot.samg_agent_id,
                "name": robot.name,
                "role": robot.role,
                "x": robot.current_position[0],
                "y": robot.current_position[1],
                "status": robot.status.value,
                "task_id": robot.assigned_task_id or "",
                "order_id": robot.current_order_id or "",
                "battery": round(robot.battery, 1),
                "cargo": f"{robot.carrying_load_kg:.0f}kg" if robot.carrying_load_kg > 0 else (robot.assigned_task_id or ""),
                "has_cargo": bool(robot.carrying_load_kg > 0 or robot.status in (RobotStatus.TRANSPORTING, RobotStatus.PICKING)),
                "heading": heading,
                "route": [[pt[0], pt[1]] for pt in robot.route] if robot.route else [],
                "color": robot.color,
            }

        congestions_frame = [
            {
                "x": alert.cell[0],
                "y": alert.cell[1],
                "severity": alert.severity,
                "robots": alert.contending_robots,
                "delay_s": round(alert.delay_penalty_s, 1),
                "description": alert.description,
            }
            for alert in step.congestion_alerts
        ]

        timeline_frames.append({
            "time_s": step.simulation_time_s,
            "robots": robots_frame,
            "congestion": congestions_frame,
            "kpis": {
                "completion_rate": step.kpis.order_completion_rate,
                "makespan_s": step.kpis.avg_fulfilment_time_s,
                "violations": step.kpis.security_violations,
                "congestion_delay_s": step.kpis.congestion_delay_s,
                "reward": step.kpis.reward,
            },
        })

    # Security event summary
    attack_info = {
        "has_attack": bool(state.security_events),
        "attack_agent": state.security_events[0]["agent"] if state.security_events else None,
        "details": state.security_events[0] if state.security_events else None,
    }

    # Allocation intervals for visual timeline
    allocations = []
    if state.allocation_plan and state.allocation_plan.feasible:
        for asgn in state.allocation_plan.assignments:
            allocations.append({
                "task_id": asgn.task_id,
                "agent_id": asgn.agent_id,
                "start_ms": asgn.start,
                "end_ms": asgn.end,
            })

    return {
        "width": layout.width,
        "height": layout.height,
        "racks": racks_data,
        "stations": stations_data,
        "frames": timeline_frames,
        "initial_frame_idx": current_step_idx,
        "auto_play": auto_play,
        "topology": state.current_topology.value if state.current_topology else "DISTRIBUTED",
        "policy_scores": state.policy_scores,
        "attack_info": attack_info,
        "allocations": allocations,
    }


def generate_3d_html(scene_data: dict[str, Any], height_px: int = 700) -> str:
    """Generate self-contained WebGL 3D warehouse application using vendored Three.js."""
    scene_json = json.dumps(scene_data)
    three_js_code = _load_static_js("three.min.js", "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js")
    orbit_js_code = _load_static_js("OrbitControls.js", "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js")

    # If vendored files were empty or not loaded, use CDN tags
    script_includes = ""
    if len(three_js_code) < 1000:
        script_includes = """
        <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
        """
    else:
        script_includes = f"""
        <script>{three_js_code}</script>
        <script>{orbit_js_code}</script>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Zero-Hour SAMG 3D Warehouse Digital Twin</title>
    {script_includes}
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; user-select: none; }}
        body {{
            background: #0B111E;
            color: #F8FAFC;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            overflow: hidden;
            width: 100vw;
            height: {height_px}px;
        }}
        #canvas-container {{
            width: 100%;
            height: 100%;
            position: relative;
        }}
        /* HUD Top Bar */
        .hud-top {{
            position: absolute;
            top: 12px;
            left: 12px;
            right: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            pointer-events: none;
            z-index: 10;
        }}
        .hud-badge {{
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid #1E293B;
            border-radius: 6px;
            padding: 8px 14px;
            backdrop-filter: blur(8px);
            pointer-events: auto;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }}
        .hud-title {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.08em;
            color: #00F0FF;
            text-transform: uppercase;
        }}
        .hud-val {{
            font-size: 15px;
            font-weight: 800;
            color: #FFFFFF;
            margin-top: 2px;
        }}
        /* Camera Controls Panel */
        .cam-controls {{
            position: absolute;
            top: 68px;
            right: 12px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            z-index: 10;
            pointer-events: auto;
        }}
        .cam-btn {{
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid #334155;
            color: #CBD5E1;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            backdrop-filter: blur(6px);
            transition: all 0.15s ease;
            text-align: left;
        }}
        .cam-btn:hover {{
            background: #1E293B;
            border-color: #00F0FF;
            color: #00F0FF;
            transform: translateX(-2px);
        }}
        .cam-btn.active {{
            background: #0F2238;
            border-color: #00F0FF;
            color: #00F0FF;
        }}
        /* Playback Timeline Bottom Bar */
        .hud-playback {{
            position: absolute;
            bottom: 14px;
            left: 12px;
            right: 12px;
            background: rgba(15, 23, 42, 0.90);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 8px 16px;
            backdrop-filter: blur(10px);
            display: flex;
            align-items: center;
            gap: 10px;
            z-index: 10;
            box-shadow: 0 4px 16px rgba(0,0,0,0.6);
        }}
        .ctrl-btn {{
            background: #1E293B;
            color: #E2E8F0;
            border: 1px solid #334155;
            width: 32px;
            height: 32px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: bold;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.12s;
        }}
        .ctrl-btn:hover {{
            background: #334155;
            border-color: #00F0FF;
            color: #00F0FF;
            transform: scale(1.05);
        }}
        .play-btn {{
            background: #00F0FF;
            color: #0B111E;
            border: none;
            width: 34px;
            height: 34px;
            border-radius: 50%;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.1s, background 0.15s;
        }}
        .play-btn:hover {{ transform: scale(1.08); background: #38BDF8; }}
        .play-btn:active {{ transform: scale(0.95); }}
        .scrubber-slider {{
            flex: 1;
            accent-color: #00F0FF;
            height: 6px;
            cursor: pointer;
        }}
        .time-label {{
            font-family: monospace;
            font-size: 13px;
            font-weight: 700;
            color: #00F0FF;
            min-width: 68px;
            text-align: center;
        }}
        .speed-btn {{
            background: transparent;
            border: 1px solid #475569;
            color: #94A3B8;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
        }}
        .speed-btn.active {{
            border-color: #00F0FF;
            color: #00F0FF;
            background: rgba(0,240,255,0.12);
        }}
        /* Telemetry Card */
        .telemetry-card {{
            position: absolute;
            bottom: 72px;
            left: 12px;
            width: 280px;
            background: rgba(11, 17, 30, 0.92);
            border: 1px solid #1E293B;
            border-left: 3px solid #00F0FF;
            border-radius: 6px;
            padding: 10px 12px;
            backdrop-filter: blur(8px);
            z-index: 10;
            box-shadow: 0 4px 14px rgba(0,0,0,0.5);
            font-size: 11px;
        }}
        .telemetry-title {{
            font-weight: 800;
            font-size: 12px;
            color: #FFFFFF;
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
        }}
        .telemetry-row {{
            display: flex;
            justify-content: space-between;
            color: #94A3B8;
            margin-top: 3px;
        }}
        .telemetry-row span.val {{
            color: #F1F5F9;
            font-weight: 600;
        }}
        /* Security Alert Banner */
        .security-badge {{
            position: absolute;
            top: 68px;
            left: 12px;
            background: rgba(69, 10, 10, 0.9);
            border: 1px solid #EF4444;
            border-radius: 6px;
            padding: 8px 12px;
            color: #FCA5A5;
            font-size: 11px;
            backdrop-filter: blur(6px);
            z-index: 10;
            display: none;
            max-width: 320px;
        }}
        .security-badge.active {{ display: block; }}
    </style>
</head>
<body>
    <div id="canvas-container">
        <!-- Top HUD -->
        <div class="hud-top">
            <div class="hud-badge">
                <div class="hud-title">SAMG Digital Twin</div>
                <div class="hud-val">Industrial Warehouse 30×20</div>
            </div>
            <div class="hud-badge">
                <div class="hud-title">Active LinUCB Arm</div>
                <div class="hud-val" id="hud-topo" style="color:#00F0FF;">DISTRIBUTED</div>
            </div>
            <div class="hud-badge">
                <div class="hud-title">ACP Trust Boundary</div>
                <div class="hud-val" id="hud-sec" style="color:#10B981;">HONEST WITNESS</div>
            </div>
            <div class="hud-badge">
                <div class="hud-title">Simulation Makespan</div>
                <div class="hud-val" id="hud-clock">0.0s</div>
            </div>
        </div>

        <!-- Camera Control Presets -->
        <div class="cam-controls">
            <button class="cam-btn active" id="btn-cam-iso" onclick="setCameraPreset('iso')">📐 Isometric (45°)</button>
            <button class="cam-btn" id="btn-cam-top" onclick="setCameraPreset('top')">🗺️ Top-Down (2D/3D)</button>
            <button class="cam-btn" id="btn-cam-follow" onclick="setCameraPreset('follow')">🎯 Chase AMR (R01)</button>
            <button class="cam-btn" id="btn-cam-attack" onclick="setCameraPreset('attack')">⚠️ Quarantine (R05)</button>
            <button class="cam-btn" id="btn-cam-reset" onclick="resetCamera()">↺ Reset View</button>
        </div>

        <!-- Security Attack HUD -->
        <div class="security-badge" id="hud-security-alert">
            <div style="font-weight: 800; color: #EF4444; margin-bottom: 2px;">⚠️ WITNESS QUARANTINE ACTIVE</div>
            <div id="sec-alert-msg">Malicious completion claim from R05 rejected by ACP.</div>
        </div>

        <!-- Selected Telemetry -->
        <div class="telemetry-card" id="telemetry-card">
            <div class="telemetry-title">
                <span id="tel-name">AMR R01 (Picker-A)</span>
                <span id="tel-status" style="color:#00F0FF;">MOVING</span>
            </div>
            <div class="telemetry-row"><span>Assigned Task:</span> <span class="val" id="tel-task">T1 (ORD-01 Pick)</span></div>
            <div class="telemetry-row"><span>Grid Position:</span> <span class="val" id="tel-pos">(12, 8)</span></div>
            <div class="telemetry-row"><span>Battery Level:</span> <span class="val" id="tel-bat">95%</span></div>
            <div class="telemetry-row"><span>Cargo Payload:</span> <span class="val" id="tel-cargo">SKU-A101</span></div>
            <div class="telemetry-row"><span>Witness Check:</span> <span class="val" id="tel-witness" style="color:#10B981;">VERIFIED ✓</span></div>
        </div>

        <!-- Playback Bottom Controls -->
        <div class="hud-playback">
            <button class="ctrl-btn" id="btn-start" onclick="jumpToStart()" title="Restart from 0.0s">⏮</button>
            <button class="play-btn" id="btn-play" onclick="togglePlay()" title="Play / Pause">▶</button>
            <button class="ctrl-btn" id="btn-end" onclick="jumpToEnd()" title="Jump to Completed">⏭</button>
            <span class="time-label" id="lbl-time">0.0s</span>
            <input type="range" class="scrubber-slider" id="scrubber" min="0" max="15" value="0" step="0.01" oninput="onScrub(this.value)" onchange="onScrub(this.value)">
            <button class="speed-btn active" id="spd-1" onclick="setSpeed(1.0)">1x</button>
            <button class="speed-btn" id="spd-2" onclick="setSpeed(2.0)">2x</button>
            <button class="speed-btn" id="spd-4" onclick="setSpeed(4.0)">4x</button>
        </div>
    </div>

    <script>
        const sceneData = {scene_json};

        // --- THREE.JS INITIALIZATION ---
        const container = document.getElementById('canvas-container');
        const width = container.clientWidth || window.innerWidth;
        const height = container.clientHeight || window.innerHeight;

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x070B14);
        scene.fog = new THREE.FogExp2(0x070B14, 0.018);

        const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: false }});
        renderer.setSize(width, height);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        container.appendChild(renderer.domElement);

        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.maxPolarAngle = Math.PI / 2.05;
        controls.minDistance = 5;
        controls.maxDistance = 90;

        // --- LIGHTING ---
        const ambientLight = new THREE.AmbientLight(0x2A3B53, 1.2);
        scene.add(ambientLight);

        const dirLight = new THREE.DirectionalLight(0xE2E8F0, 1.5);
        dirLight.position.set(15, 35, 20);
        dirLight.castShadow = true;
        dirLight.shadow.mapSize.width = 2048;
        dirLight.shadow.mapSize.height = 2048;
        dirLight.shadow.camera.near = 0.5;
        dirLight.shadow.camera.far = 100;
        dirLight.shadow.camera.left = -25;
        dirLight.shadow.camera.right = 25;
        dirLight.shadow.camera.top = 25;
        dirLight.shadow.camera.bottom = -25;
        scene.add(dirLight);

        const blueLight = new THREE.PointLight(0x00F0FF, 1.5, 40);
        blueLight.position.set(0, 12, 0);
        scene.add(blueLight);

        const orangeLight = new THREE.PointLight(0xF59E0B, 1.0, 30);
        orangeLight.position.set(25, 8, 10);
        scene.add(orangeLight);

        // --- COORDINATE SYSTEM ---
        const SCALE = 1.6;
        function toWorld(gx, gy, h = 0) {{
            return new THREE.Vector3((gx - sceneData.width / 2 + 0.5) * SCALE, h, (gy - sceneData.height / 2 + 0.5) * SCALE);
        }}

        // --- 1. FLOOR & ZONES ---
        const floorGeo = new THREE.PlaneGeometry(sceneData.width * SCALE + 8, sceneData.height * SCALE + 8);
        const floorMat = new THREE.MeshStandardMaterial({{
            color: 0x0D1525,
            roughness: 0.85,
            metalness: 0.2,
        }});
        const floor = new THREE.Mesh(floorGeo, floorMat);
        floor.rotation.x = -Math.PI / 2;
        floor.receiveShadow = true;
        scene.add(floor);

        const gridHelper = new THREE.GridHelper(sceneData.width * SCALE, sceneData.width, 0x1E293B, 0x141E33);
        gridHelper.position.y = 0.01;
        scene.add(gridHelper);

        function createZoneFloor(minX, maxX, minY, maxY, colorHex, opacity = 0.15) {{
            const w = (maxX - minX + 1) * SCALE;
            const h = (maxY - minY + 1) * SCALE;
            const geo = new THREE.PlaneGeometry(w, h);
            const mat = new THREE.MeshBasicMaterial({{
                color: colorHex,
                transparent: true,
                opacity: opacity,
                side: THREE.DoubleSide
            }});
            const mesh = new THREE.Mesh(geo, mat);
            mesh.rotation.x = -Math.PI / 2;
            const center = toWorld((minX + maxX) / 2, (minY + maxY) / 2, 0.02);
            mesh.position.copy(center);
            scene.add(mesh);
        }}

        createZoneFloor(1, 4, 1, 18, 0x0284C7, 0.18);
        createZoneFloor(24, 27, 1, 12, 0x10B981, 0.18);
        createZoneFloor(24, 28, 14, 18, 0x8B5CF6, 0.22);
        createZoneFloor(1, 4, 16, 18, 0xF59E0B, 0.25);

        // --- 2. STORAGE RACKS ---
        const rackGroup = new THREE.Group();
        scene.add(rackGroup);

        const steelMat = new THREE.MeshStandardMaterial({{ color: 0x334155, roughness: 0.5, metalness: 0.8 }});
        const beamMat = new THREE.MeshStandardMaterial({{ color: 0xF59E0B, roughness: 0.6, metalness: 0.4 }});
        const toteColors = [0x0284C7, 0x10B981, 0xEF4444, 0xF59E0B, 0x6366F1];

        sceneData.racks.forEach(r => {{
            const x1 = r.x_min, x2 = r.x_max, y1 = r.y_min, y2 = r.y_max;
            const rWidth = (x2 - x1 + 1) * SCALE;
            const rDepth = (y2 - y1 + 1) * SCALE;
            const rHeight = 3.8;
            const center = toWorld((x1 + x2) / 2, (y1 + y2) / 2, 0);

            const singleRack = new THREE.Group();
            singleRack.position.copy(center);

            const postGeo = new THREE.BoxGeometry(0.08, rHeight, 0.08);
            const halfW = rWidth / 2 - 0.06;
            const halfD = rDepth / 2 - 0.06;
            const postOffsets = [
                [-halfW, -halfD], [halfW, -halfD],
                [-halfW, halfD], [halfW, halfD]
            ];
            postOffsets.forEach(([ox, oz]) => {{
                const post = new THREE.Mesh(postGeo, steelMat);
                post.position.set(ox, rHeight / 2, oz);
                post.castShadow = true;
                singleRack.add(post);
            }});

            const shelfLevels = [0.8, 2.0, 3.2];
            shelfLevels.forEach((levelY, sIdx) => {{
                const beamGeo = new THREE.BoxGeometry(rWidth, 0.08, 0.04);
                const frontBeam = new THREE.Mesh(beamGeo, beamMat);
                frontBeam.position.set(0, levelY, halfD);
                singleRack.add(frontBeam);

                const backBeam = new THREE.Mesh(beamGeo, beamMat);
                backBeam.position.set(0, levelY, -halfD);
                singleRack.add(backBeam);

                const deckGeo = new THREE.BoxGeometry(rWidth - 0.1, 0.02, rDepth - 0.1);
                const deck = new THREE.Mesh(deckGeo, steelMat);
                deck.position.set(0, levelY - 0.02, 0);
                singleRack.add(deck);

                const toteGeo = new THREE.BoxGeometry(rWidth * 0.38, 0.45, rDepth * 0.7);
                [-rWidth * 0.22, rWidth * 0.22].forEach((tx, bIdx) => {{
                    const colorIdx = (sIdx * 2 + bIdx + r.id.charCodeAt(r.id.length - 1)) % toteColors.length;
                    const toteMat = new THREE.MeshStandardMaterial({{
                        color: toteColors[colorIdx],
                        roughness: 0.3,
                        metalness: 0.1
                    }});
                    const tote = new THREE.Mesh(toteGeo, toteMat);
                    tote.position.set(tx, levelY + 0.23, 0);
                    tote.castShadow = true;
                    singleRack.add(tote);
                }});
            }});

            rackGroup.add(singleRack);
        }});

        // --- 3. AUTONOMOUS MOBILE ROBOTS (AMRs) ---
        const robotMeshes = {{}};
        const pathLines = {{}};
        const robotGroup = new THREE.Group();
        scene.add(robotGroup);

        const amrBodyGeo = new THREE.CylinderGeometry(0.55, 0.58, 0.28, 24);
        const amrBodyMat = new THREE.MeshStandardMaterial({{ color: 0x1E293B, roughness: 0.4, metalness: 0.7 }});
        const wheelGeo = new THREE.CylinderGeometry(0.14, 0.14, 0.08, 16);
        const wheelMat = new THREE.MeshStandardMaterial({{ color: 0x0F172A, roughness: 0.9 }});
        const lidarGeo = new THREE.CylinderGeometry(0.12, 0.12, 0.12, 16);
        const lidarMat = new THREE.MeshStandardMaterial({{ color: 0x00F0FF, emissive: 0x00F0FF, emissiveIntensity: 0.5 }});
        const cargoGeo = new THREE.BoxGeometry(0.65, 0.45, 0.65);
        const cargoMat = new THREE.MeshStandardMaterial({{ color: 0xD97706, roughness: 0.6 }});

        function createAMRModel(robotId, colorHex) {{
            const group = new THREE.Group();

            // Main chassis
            const body = new THREE.Mesh(amrBodyGeo, amrBodyMat);
            body.position.y = 0.24;
            body.castShadow = true;
            group.add(body);

            // Colored Safety Ring
            const accentGeo = new THREE.TorusGeometry(0.56, 0.03, 8, 32);
            const accentMat = new THREE.MeshBasicMaterial({{ color: colorHex }});
            const accent = new THREE.Mesh(accentGeo, accentMat);
            accent.rotation.x = Math.PI / 2;
            accent.position.y = 0.26;
            group.add(accent);

            // Drive Wheels
            [-0.52, 0.52].forEach(wx => {{
                const wheel = new THREE.Mesh(wheelGeo, wheelMat);
                wheel.rotation.z = Math.PI / 2;
                wheel.position.set(wx, 0.14, 0);
                group.add(wheel);
            }});

            // Top rotating LIDAR puck
            const lidar = new THREE.Mesh(lidarGeo, lidarMat);
            lidar.position.y = 0.44;
            group.add(lidar);
            group.userData.lidar = lidar;

            // Halo Light underneath
            const haloGeo = new THREE.RingGeometry(0.4, 0.75, 32);
            const haloMat = new THREE.MeshBasicMaterial({{
                color: colorHex,
                transparent: true,
                opacity: 0.6,
                side: THREE.DoubleSide
            }});
            const halo = new THREE.Mesh(haloGeo, haloMat);
            halo.rotation.x = -Math.PI / 2;
            halo.position.y = 0.03;
            group.add(halo);
            group.userData.halo = halo;

            // Visible Cargo Box
            const cargo = new THREE.Mesh(cargoGeo, cargoMat);
            cargo.position.y = 0.62;
            cargo.castShadow = true;
            cargo.visible = false;
            group.add(cargo);
            group.userData.cargo = cargo;

            // Floating 3D Text Badge / Sprite
            const canvas = document.createElement('canvas');
            canvas.width = 256;
            canvas.height = 64;
            const ctx = canvas.getContext('2d');

            function drawBadge(id, st, tId) {{
                ctx.clearRect(0, 0, 256, 64);
                ctx.fillStyle = 'rgba(11, 17, 30, 0.88)';
                ctx.strokeStyle = colorHex;
                ctx.lineWidth = 4;
                ctx.fillRect(4, 4, 248, 56);
                ctx.strokeRect(4, 4, 248, 56);

                ctx.fillStyle = '#FFFFFF';
                ctx.font = 'bold 22px monospace';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                const label = tId ? `${{id}}: ${{tId}}` : `${{id}} [${{st}}]`;
                ctx.fillText(label, 128, 32);
            }}

            drawBadge(robotId, 'IDLE', '');
            const spriteTex = new THREE.CanvasTexture(canvas);
            const spriteMat = new THREE.SpriteMaterial({{ map: spriteTex, depthTest: false }});
            const sprite = new THREE.Sprite(spriteMat);
            sprite.scale.set(2.2, 0.55, 1.0);
            sprite.position.y = 1.25;
            group.add(sprite);

            group.userData.updateSprite = function(id, st, tId) {{
                drawBadge(id, st, tId);
                spriteTex.needsUpdate = true;
            }};

            return group;
        }}

        // Instantiate AMRs
        const initialFrame = sceneData.frames[sceneData.initial_frame_idx || 0];
        Object.keys(initialFrame.robots).forEach(rId => {{
            const rData = initialFrame.robots[rId];
            const amrMesh = createAMRModel(rId, rData.color || 0x00F0FF);
            const pos = toWorld(rData.x, rData.y, 0);
            amrMesh.position.copy(pos);
            amrMesh.rotation.y = rData.heading || 0;
            robotGroup.add(amrMesh);
            robotMeshes[rId] = amrMesh;

            // Route Polyline
            const lineMat = new THREE.LineDashedMaterial({{
                color: rData.color || 0x00F0FF,
                dashSize: 0.4,
                gapSize: 0.2,
                linewidth: 2,
            }});
            const lineGeo = new THREE.BufferGeometry();
            const line = new THREE.Line(lineGeo, lineMat);
            scene.add(line);
            pathLines[rId] = line;
        }});

        // --- 4. CONGESTION VOLUMES ---
        const congestionMeshGroup = new THREE.Group();
        scene.add(congestionMeshGroup);
        const congGeo = new THREE.CylinderGeometry(0.9, 0.9, 2.0, 24, 1, true);
        const congMat = new THREE.MeshBasicMaterial({{
            color: 0xEF4444,
            transparent: true,
            opacity: 0.35,
            side: THREE.DoubleSide
        }});

        function updateCongestionVolumes(congestionList) {{
            while (congestionMeshGroup.children.length > 0) {{
                congestionMeshGroup.remove(congestionMeshGroup.children[0]);
            }}
            congestionList.forEach(c => {{
                const mesh = new THREE.Mesh(congGeo, congMat);
                mesh.position.copy(toWorld(c.x, c.y, 1.0));
                congestionMeshGroup.add(mesh);
            }});
        }}

        // --- 5. CAMERA PRESETS & NAVIGATION ---
        let currentCamPreset = 'iso';
        let followTargetRobotId = 'R01';

        function setCameraPreset(mode) {{
            currentCamPreset = mode;
            document.querySelectorAll('.cam-btn').forEach(b => b.classList.remove('active'));

            if (mode === 'iso') {{
                document.getElementById('btn-cam-iso').classList.add('active');
                camera.position.set(0, 32, 28);
                controls.target.set(0, 0, 0);
            }} else if (mode === 'top') {{
                document.getElementById('btn-cam-top').classList.add('active');
                camera.position.set(0, 48, 0.1);
                controls.target.set(0, 0, 0);
            }} else if (mode === 'follow') {{
                document.getElementById('btn-cam-follow').classList.add('active');
                followTargetRobotId = 'R01';
            }} else if (mode === 'attack') {{
                document.getElementById('btn-cam-attack').classList.add('active');
                followTargetRobotId = sceneData.attack_info.attack_agent || 'R05';
            }}
            controls.update();
        }}

        function resetCamera() {{
            setCameraPreset('iso');
        }}

        setCameraPreset('iso');

        // --- 6. TIMELINE & SIMULATION PLAYBACK ---
        const totalFrames = sceneData.frames.length;
        const maxTime = sceneData.frames[totalFrames - 1].time_s || 60.0;

        const scrubber = document.getElementById('scrubber');
        scrubber.max = (totalFrames - 1).toString();
        const startIdx = Math.max(0, Math.min(parseInt(sceneData.initial_frame_idx || 0), totalFrames - 1));
        scrubber.value = startIdx.toString();

        let currentFrameVal = parseFloat(startIdx);
        let playbackTime = 0.0;
        let playbackSpeed = 1.0;
        let isPlaying = Boolean(sceneData.auto_play);

        if (isPlaying) {{
            document.getElementById('btn-play').textContent = '⏸';
        }}

        function togglePlay() {{
            if (currentFrameVal >= totalFrames - 1 - 0.05) {{
                currentFrameVal = 0;
                scrubber.value = "0";
                applyFrame(0);
            }}
            isPlaying = !isPlaying;
            document.getElementById('btn-play').textContent = isPlaying ? '⏸' : '▶';
        }}

        function jumpToStart() {{
            isPlaying = false;
            document.getElementById('btn-play').textContent = '▶';
            currentFrameVal = 0;
            scrubber.value = "0";
            applyFrame(0);
        }}

        function jumpToEnd() {{
            isPlaying = false;
            document.getElementById('btn-play').textContent = '▶';
            currentFrameVal = totalFrames - 1;
            scrubber.value = (totalFrames - 1).toString();
            applyFrame(totalFrames - 1);
        }}

        function setSpeed(spd) {{
            playbackSpeed = spd;
            ['spd-1', 'spd-2', 'spd-4'].forEach(id => document.getElementById(id).classList.remove('active'));
            if (spd === 1.0) document.getElementById('spd-1').classList.add('active');
            if (spd === 2.0) document.getElementById('spd-2').classList.add('active');
            if (spd === 4.0) document.getElementById('spd-4').classList.add('active');
        }}

        function onScrub(val) {{
            isPlaying = false;
            document.getElementById('btn-play').textContent = '▶';
            const fVal = Math.max(0, Math.min(parseFloat(val) || 0, totalFrames - 1));
            currentFrameVal = fVal;
            scrubber.value = fVal.toString();
            applyFrame(fVal);
        }}

        // Continuous linear interpolation across discrete simulation checkpoints
        function applyFrame(frameVal) {{
            const baseIdx = Math.max(0, Math.min(Math.floor(frameVal), totalFrames - 1));
            const nextIdx = Math.min(baseIdx + 1, totalFrames - 1);
            const alpha = frameVal - baseIdx;

            const fA = sceneData.frames[baseIdx];
            const fB = sceneData.frames[nextIdx];

            playbackTime = fA.time_s + alpha * (fB.time_s - fA.time_s);
            document.getElementById('lbl-time').textContent = playbackTime.toFixed(1) + 's';
            document.getElementById('hud-clock').textContent = playbackTime.toFixed(1) + 's';

            // Update AMRs
            Object.keys(fA.robots).forEach(rId => {{
                const rA = fA.robots[rId];
                const rB = fB.robots[rId] || rA;
                const mesh = robotMeshes[rId];
                if (!mesh) return;

                // Position interpolation
                const curX = rA.x + alpha * (rB.x - rA.x);
                const curY = rA.y + alpha * (rB.y - rA.y);
                mesh.position.copy(toWorld(curX, curY, 0));

                // Smooth Rotation towards movement direction
                const dx = rB.x - rA.x;
                const dy = rB.y - rA.y;
                if (Math.abs(dx) > 0.01 || Math.abs(dy) > 0.01) {{
                    const targetAngle = Math.atan2(dx, dy);
                    mesh.rotation.y = targetAngle;
                }}

                // Status & Cargo
                const status = (alpha > 0.5) ? rB.status : rA.status;
                const task = (alpha > 0.5) ? rB.task_id : rA.task_id;
                const hasCargo = (alpha > 0.5) ? rB.has_cargo : rA.has_cargo;
                if (mesh.userData.cargo) {{
                    mesh.userData.cargo.visible = hasCargo;
                }}

                // Status Underglow Halo
                if (mesh.userData.halo) {{
                    if (sceneData.attack_info.has_attack && rId === sceneData.attack_info.attack_agent) {{
                        mesh.userData.halo.material.color.setHex(0xEF4444);
                    }} else if (status === 'COMPLETED') {{
                        mesh.userData.halo.material.color.setHex(0x10B981);
                    }} else if (status === 'CONGESTED' || status === 'WAITING') {{
                        mesh.userData.halo.material.color.setHex(0xF59E0B);
                    }} else if (status === 'PICKING' || status === 'TRANSPORTING') {{
                        mesh.userData.halo.material.color.setHex(0x38BDF8);
                    }} else {{
                        mesh.userData.halo.material.color.setHex(0x00F0FF);
                    }}
                }}

                // 3D Floating Nameplate
                if (mesh.userData.updateSprite) {{
                    mesh.userData.updateSprite(rId, status, task);
                }}

                // Route update
                const activeRoute = (alpha > 0.5) ? rB.route : rA.route;
                if (pathLines[rId]) {{
                    if (activeRoute && activeRoute.length > 1) {{
                        const pts = [mesh.position.clone().setY(0.08)];
                        activeRoute.forEach(pt => pts.push(toWorld(pt[0], pt[1], 0.08)));
                        pathLines[rId].geometry.dispose();
                        pathLines[rId].geometry = new THREE.BufferGeometry().setFromPoints(pts);
                        pathLines[rId].computeLineDistances();
                        pathLines[rId].visible = true;
                    }} else {{
                        pathLines[rId].visible = false;
                    }}
                }}
            }});

            // Congestion
            updateCongestionVolumes((alpha > 0.5) ? fB.congestion : fA.congestion);

            // Telemetry Card
            const currentRobots = (alpha > 0.5) ? fB.robots : fA.robots;
            const trackedRobot = currentRobots[followTargetRobotId] || currentRobots['R01'];
            if (trackedRobot) {{
                document.getElementById('tel-name').textContent = `AMR ${{trackedRobot.id}} (${{trackedRobot.role}})`;
                document.getElementById('tel-status').textContent = trackedRobot.status;
                document.getElementById('tel-task').textContent = trackedRobot.task_id || 'IDLE';
                document.getElementById('tel-pos').textContent = `(${{trackedRobot.x}}, ${{trackedRobot.y}})`;
                document.getElementById('tel-bat').textContent = `${{trackedRobot.battery}}%`;
                document.getElementById('tel-cargo').textContent = trackedRobot.cargo || 'NONE';

                if (sceneData.attack_info.has_attack && trackedRobot.id === sceneData.attack_info.attack_agent) {{
                    document.getElementById('tel-witness').textContent = 'DISPUTED & QUARANTINED ⚠️';
                    document.getElementById('tel-witness').style.color = '#EF4444';
                    document.getElementById('hud-security-alert').classList.add('active');
                }} else {{
                    document.getElementById('tel-witness').textContent = 'VERIFIED BY WITNESS ✓';
                    document.getElementById('tel-witness').style.color = '#10B981';
                    document.getElementById('hud-security-alert').classList.remove('active');
                }}
            }}
        }}

        // --- 7. MAIN ANIMATION LOOP ---
        let lastTime = performance.now();

        function animate(now) {{
            requestAnimationFrame(animate);
            const dt = (now - lastTime) / 1000.0;
            lastTime = now;

            // Spin lidar pucks
            Object.values(robotMeshes).forEach(m => {{
                if (m.userData.lidar) m.userData.lidar.rotation.y += 0.08;
            }});

            // Follow mode camera tracking
            if ((currentCamPreset === 'follow' || currentCamPreset === 'attack') && robotMeshes[followTargetRobotId]) {{
                const targetPos = robotMeshes[followTargetRobotId].position;
                controls.target.lerp(targetPos, 0.08);
                const desiredCamPos = targetPos.clone().add(new THREE.Vector3(0, 10, 12));
                camera.position.lerp(desiredCamPos, 0.08);
            }}

            // Playback progress
            if (isPlaying) {{
                const stepRate = 1.0 * playbackSpeed;
                currentFrameVal += dt * stepRate;
                if (currentFrameVal >= totalFrames - 1) {{
                    currentFrameVal = totalFrames - 1;
                    isPlaying = false;
                    document.getElementById('btn-play').textContent = '▶';
                }}
                scrubber.value = currentFrameVal.toFixed(2);
                applyFrame(currentFrameVal);
            }}

            controls.update();
            renderer.render(scene, camera);
        }}

        // Initial render frame
        applyFrame(currentFrameVal);
        document.getElementById('hud-topo').textContent = sceneData.topology;
        requestAnimationFrame(animate);

        window.addEventListener('resize', () => {{
            const w = container.clientWidth;
            const h = container.clientHeight;
            camera.aspect = w / h;
            camera.updateProjectionMatrix();
            renderer.setSize(w, h);
        }});
    </script>
</body>
</html>
"""


def render_3d_viewport(
    state: WarehouseState,
    steps: list[WarehouseState] | None = None,
    active_step_idx: int = 0,
    auto_play: bool = False,
    height_px: int = 720,
) -> None:
    """Render interactive 3D WebGL warehouse digital twin via Streamlit HTML component."""
    scene_data = serialize_warehouse_scene(state, steps, active_step_idx, auto_play=auto_play)
    html_code = generate_3d_html(scene_data, height_px=height_px)
    st.components.v1.html(html_code, height=height_px, scrolling=False)
