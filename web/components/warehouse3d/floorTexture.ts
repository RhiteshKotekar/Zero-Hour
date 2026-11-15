// Paints the static floor plan (zones, lanes, aisles, markings, labels) into one canvas texture:
// a single draw call, crisp labels, no font downloads.
import * as THREE from "three";
import type { Layout, Robot } from "@/lib/types";
import { C, ZONE_TINT } from "./palette";

export const FLOOR_MARGIN = 1;
const PX = 64; // pixels per metre

export function makeFloorTexture(layout: Layout, robots: Robot[]): THREE.CanvasTexture {
  const W = layout.width + FLOOR_MARGIN * 2;
  const H = layout.height + FLOOR_MARGIN * 2;
  const cv = document.createElement("canvas");
  cv.width = W * PX;
  cv.height = H * PX;
  const g = cv.getContext("2d")!;
  g.scale(PX, PX);
  g.translate(FLOOR_MARGIN, FLOOR_MARGIN);
  const font = (size: number, weight = 700) => `${weight} ${size}px Inter, "Segoe UI", system-ui, sans-serif`;
  const rect = (r: number[], pad = 0) => [r[0] + pad, r[1] + pad, r[2] - r[0] + 1 - 2 * pad, r[3] - r[1] + 1 - 2 * pad] as const;

  // outside apron + building slab
  g.fillStyle = C.floorOut;
  g.fillRect(-FLOOR_MARGIN, -FLOOR_MARGIN, W, H);
  g.fillStyle = C.floor;
  g.fillRect(0, 0, layout.width, layout.height);

  // zone tints
  for (const z of layout.zones) {
    const tint = ZONE_TINT[z.id];
    if (!tint || z.id.endsWith("AISLE")) continue;
    g.fillStyle = tint;
    g.fillRect(...rect(z.rect, 0.06));
  }

  // 1 m grid
  g.strokeStyle = C.grid;
  g.lineWidth = 0.02;
  g.beginPath();
  for (let x = 0; x <= layout.width; x++) {
    g.moveTo(x, 0);
    g.lineTo(x, layout.height);
  }
  for (let y = 0; y <= layout.height; y++) {
    g.moveTo(0, y);
    g.lineTo(layout.width, y);
  }
  g.stroke();

  // main aisles (two-way travel lanes)
  for (const z of layout.zones) {
    if (!z.id.endsWith("AISLE")) continue;
    const [x, y, w, h] = rect(z.rect);
    g.fillStyle = "#f5f6f8";
    g.fillRect(x, y + 0.05, w, h - 0.1);
    g.strokeStyle = C.lane;
    g.lineWidth = 0.06;
    g.setLineDash([]);
    g.beginPath();
    g.moveTo(x + 0.1, y + 0.08);
    g.lineTo(x + w - 0.1, y + 0.08);
    g.moveTo(x + 0.1, y + h - 0.08);
    g.lineTo(x + w - 0.1, y + h - 0.08);
    g.stroke();
    g.setLineDash([0.5, 0.35]);
    g.lineWidth = 0.05;
    g.beginPath();
    g.moveTo(x + 0.3, y + h / 2);
    g.lineTo(x + w - 0.3, y + h / 2);
    g.stroke();
    g.setLineDash([]);
    // direction chevrons
    g.fillStyle = "rgba(232,177,58,0.55)";
    for (let cx = x + 2; cx < x + w - 1; cx += 6) {
      for (const [cy, dir] of [
        [y + h * 0.27, 1],
        [y + h * 0.73, -1],
      ] as const) {
        g.beginPath();
        g.moveTo(cx - 0.18 * dir, cy - 0.16);
        g.lineTo(cx + 0.18 * dir, cy);
        g.lineTo(cx - 0.18 * dir, cy + 0.16);
        g.closePath();
        g.fill();
      }
    }
    g.fillStyle = C.muted;
    g.font = font(0.34);
    g.textBaseline = "middle";
    g.fillText(z.label.toUpperCase(), x + 0.3, y + h * 0.27);
  }

  // rack footprints
  for (const r of layout.racks) {
    g.fillStyle = "#d9dee5";
    g.fillRect(...rect(r.rect, 0.04));
  }

  // single-lane narrow aisles
  for (const a of layout.aisles) {
    const [x, y, w, h] = rect(a.rect);
    if (a.blocked) {
      g.save();
      g.beginPath();
      g.rect(x, y, w, h);
      g.clip();
      g.fillStyle = "#fde2e2";
      g.fillRect(x, y, w, h);
      g.strokeStyle = "#e45d5d";
      g.lineWidth = 0.12;
      for (let k = -2; k < h + 2; k += 0.45) {
        g.beginPath();
        g.moveTo(x, y + k);
        g.lineTo(x + w, y + k + w);
        g.stroke();
      }
      g.restore();
    } else {
      g.fillStyle = "#f8f9fb";
      g.fillRect(x + 0.04, y, w - 0.08, h);
    }
    g.strokeStyle = a.blocked ? C.bad : C.lane;
    g.lineWidth = 0.05;
    g.beginPath();
    g.moveTo(x + 0.08, y);
    g.lineTo(x + 0.08, y + h);
    g.moveTo(x + w - 0.08, y);
    g.lineTo(x + w - 0.08, y + h);
    g.stroke();
    // entry stop bars
    g.lineWidth = 0.08;
    g.beginPath();
    g.moveTo(x + 0.1, y + 0.06);
    g.lineTo(x + w - 0.1, y + 0.06);
    g.moveTo(x + 0.1, y + h - 0.06);
    g.lineTo(x + w - 0.1, y + h - 0.06);
    g.stroke();
    g.fillStyle = a.blocked ? C.bad : "#97a1b1";
    g.font = font(0.3, 800);
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText(a.id, x + w / 2, y + 0.45);
    g.fillText(a.id, x + w / 2, y + h - 0.45);
    // vertical "SINGLE LANE" marking
    g.save();
    g.translate(x + w / 2, y + h / 2);
    g.rotate(-Math.PI / 2);
    g.font = font(0.2, 700);
    g.fillStyle = a.blocked ? C.bad : "rgba(151,161,177,0.8)";
    g.fillText(a.blocked ? "BLOCKED" : "SINGLE LANE", 0, 0);
    g.restore();
    g.textAlign = "left";
  }

  // robot parking bays
  g.setLineDash([0.18, 0.1]);
  for (const r of robots) {
    if (!r.mobile) continue;
    const [x, y] = r.home;
    g.strokeStyle = "#aab4c3";
    g.lineWidth = 0.04;
    g.strokeRect(x + 0.08, y + 0.08, 0.84, 0.84);
    g.fillStyle = "#a3adbd";
    g.font = font(0.17, 700);
    g.textAlign = "center";
    g.fillText(r.id, x + 0.5, y + 0.88);
    g.textAlign = "left";
  }
  g.setLineDash([]);

  // stations
  for (const st of layout.stations) {
    const [x, y, w, h] = rect(st.rect);
    if (st.kind === "pack") {
      g.fillStyle = "#ffffff";
      g.fillRect(x + 0.08, y + 0.08, w - 0.16, h - 0.16);
      g.strokeStyle = "#a78bfa";
      g.lineWidth = 0.06;
      g.strokeRect(x + 0.08, y + 0.08, w - 0.16, h - 0.16);
      g.fillStyle = "#6d28d9";
      g.font = font(0.3, 800);
      g.textAlign = "center";
      g.fillText(st.label.replace("Pack station ", "PACK ").toUpperCase(), x + w / 2, y + 0.38);
      g.textAlign = "left";
    } else if (st.kind === "dock") {
      // hazard-striped dock apron
      g.save();
      g.beginPath();
      g.rect(x, y + 0.15, w, h - 0.15);
      g.clip();
      g.fillStyle = "#fbd38d";
      g.fillRect(x, y, w, h);
      g.strokeStyle = "#1f2937";
      g.lineWidth = 0.16;
      for (let k = -2; k < w + 2; k += 0.5) {
        g.beginPath();
        g.moveTo(x + k, y + h);
        g.lineTo(x + k + 1, y);
        g.stroke();
      }
      g.restore();
      g.fillStyle = "#9a3412";
      g.font = font(0.3, 800);
      g.textAlign = "center";
      g.fillText(st.label.toUpperCase(), x + w / 2, y - 0.25);
      g.textAlign = "left";
    } else {
      g.fillStyle = "#e3f6ec";
      g.fillRect(x + 0.1, y + 0.1, w - 0.2, h - 0.2);
      g.strokeStyle = "#6ee7b7";
      g.lineWidth = 0.05;
      g.strokeRect(x + 0.1, y + 0.1, w - 0.2, h - 0.2);
      g.fillStyle = "#047857";
      g.font = font(0.24, 800);
      g.textAlign = "center";
      g.fillText("CHARGING", x + w / 2, y + h - 0.25);
      g.textAlign = "left";
    }
  }

  // consolidation points
  for (const c of layout.consolidation) {
    const [x, y] = c.cell;
    g.fillStyle = "#ffffff";
    g.fillRect(x + 0.1, y + 0.1, 0.8, 0.8);
    g.strokeStyle = C.amber;
    g.lineWidth = 0.05;
    g.setLineDash([0.14, 0.08]);
    g.strokeRect(x + 0.1, y + 0.1, 0.8, 0.8);
    g.setLineDash([]);
    g.fillStyle = "#b45309";
    g.font = font(0.22, 800);
    g.textAlign = "center";
    g.fillText(c.id, x + 0.5, y - 0.12 + 0.3);
    g.textAlign = "left";
  }

  // zone labels
  for (const z of layout.zones) {
    if (z.id === "STORAGE" || z.id.endsWith("AISLE")) continue;
    const [x0, y0, x1] = z.rect;
    const label = z.label.toUpperCase();
    const size = Math.min(0.42, (x1 - x0 + 0.6) / (label.length * 0.62));
    g.fillStyle = C.muted;
    g.font = font(size, 800);
    g.textBaseline = "alphabetic";
    g.fillText(label, x0 + 0.25, y0 + 0.2 + size);
  }

  // building outline
  g.strokeStyle = "#b8c0cc";
  g.lineWidth = 0.08;
  g.strokeRect(0, 0, layout.width, layout.height);

  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  tex.generateMipmaps = true;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  return tex;
}
