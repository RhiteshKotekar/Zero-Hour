"use client";
import { useEffect, useMemo, useRef } from "react";
import { Html } from "@react-three/drei";
import { labelPortal } from "./labelPortal";
import type { InventoryItem, Layout } from "@/lib/types";
import { useStore } from "@/lib/store";
import { BIN_COLORS, C, RACK_H, SHELF_Y, hash01 } from "./palette";
import { InstancedBoxes, type BoxSpec, type InstancedBoxesHandle } from "./InstancedBoxes";

const SKU_LEVEL = 1; // inventory bins sit on the second shelf (pick height)

interface Built {
  uprights: BoxSpec[];
  beams: BoxSpec[];
  decks: BoxSpec[];
  bins: BoxSpec[];
  /** sku → bin instance index */
  skuBin: Map<string, number>;
  binBase: string[];
}

function build(layout: Layout, inventory: InventoryItem[]): Built {
  const uprights: BoxSpec[] = [];
  const beams: BoxSpec[] = [];
  const decks: BoxSpec[] = [];
  const bins: BoxSpec[] = [];
  const skuBin = new Map<string, number>();
  const binBase: string[] = [];
  const invByCell = new Map(inventory.map((s) => [`${s.cell[0]},${s.cell[1]}`, s]));

  for (const r of layout.racks) {
    const [x0, y0, x1, y1] = r.rect;
    const z0 = y0 + 0.05,
      z1 = y1 + 0.95,
      depth = z1 - z0;
    for (let gx = x0; gx <= x1; gx++) {
      const xa = gx + 0.1,
        xb = gx + 0.9;
      // uprights every 2 m
      for (let z = z0; z <= z1 + 1e-6; z += Math.min(2, depth)) {
        const zz = Math.min(z, z1);
        for (const x of [xa, xb]) uprights.push({ p: [x, RACK_H / 2, zz], s: [0.07, RACK_H, 0.07] });
      }
      if ((z1 - z0) % 2 > 1e-6) for (const x of [xa, xb]) uprights.push({ p: [x, RACK_H / 2, z1], s: [0.07, RACK_H, 0.07] });
      for (const [li, y] of SHELF_Y.entries()) {
        for (const x of [xa, xb]) beams.push({ p: [x, y + 0.04, (z0 + z1) / 2], s: [0.05, 0.08, depth] });
        decks.push({ p: [gx + 0.5, y + 0.085, (z0 + z1) / 2], s: [0.78, 0.025, depth - 0.02] });
        // bins per cell
        for (let gy = y0; gy <= y1; gy++) {
          const inv = invByCell.get(`${gx},${gy}`);
          const isSku = inv && li === SKU_LEVEL;
          if (!isSku && hash01(gx, gy, li) < 0.22) continue; // empty slots
          const hgt = li === SHELF_Y.length - 1 ? 0.3 : 0.38;
          const col = isSku ? "#9aa7bd" : BIN_COLORS[Math.floor(hash01(gy, gx, li + 7) * BIN_COLORS.length)];
          if (isSku) skuBin.set(inv.sku, bins.length);
          binBase.push(col);
          bins.push({ p: [gx + 0.5, y + 0.1 + hgt / 2, gy + 0.5], s: [0.62, hgt, 0.78], c: col });
        }
      }
    }
  }
  return { uprights, beams, decks, bins, skuBin, binBase };
}

/**
 * Instanced racks: uprights, beams, decking, bins. `neededSkus` (SKUs still to be picked at t) are highlighted;
 * out-of-stock SKUs are red.
 */
export function Racks({ layout, inventory, neededSkus }: { layout: Layout; inventory: InventoryItem[]; neededSkus: string[] }) {
  const b = useMemo(() => build(layout, inventory), [layout, inventory]);
  const binsRef = useRef<InstancedBoxesHandle>(null);
  const select = useStore((s) => s.select);
  const setHover = useStore((s) => s.setHover);
  const key = neededSkus.join("|");

  useEffect(() => {
    const h = binsRef.current;
    if (!h) return;
    const need = new Set(neededSkus);
    for (const s of inventory) {
      const i = b.skuBin.get(s.sku);
      if (i == null) continue;
      h.setColor(i, s.stock === 0 ? C.bad : need.has(s.sku) ? C.amber : b.binBase[i]);
    }
    h.commitColors();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, b, inventory]);

  const needed = useMemo(() => new Set(neededSkus), [neededSkus]);

  return (
    <group>
      <InstancedBoxes boxes={b.uprights} color={C.upright} metalness={0.25} roughness={0.55} />
      <InstancedBoxes boxes={b.beams} color={C.beam} metalness={0.2} roughness={0.6} />
      <InstancedBoxes boxes={b.decks} color={C.deck} roughness={0.85} castShadow={false} />
      <InstancedBoxes ref={binsRef} boxes={b.bins} roughness={0.75} />
      {/* rack hitboxes + labels */}
      {layout.racks.map((r) => {
        const [x0, y0, x1, y1] = r.rect;
        const cx = (x0 + x1 + 1) / 2,
          cz = (y0 + y1 + 1) / 2;
        return (
          <group key={r.id}>
            <mesh
              position={[cx, RACK_H / 2, cz]}
              onClick={(e) => {
                e.stopPropagation();
                select({ kind: "rack", id: r.id });
              }}
              onPointerOver={(e) => {
                e.stopPropagation();
                setHover({ kind: "rack", id: r.id });
              }}
              onPointerOut={() => setHover(null)}
            >
              <boxGeometry args={[x1 - x0 + 1, RACK_H, y1 - y0 + 1]} />
              <meshBasicMaterial transparent opacity={0} depthWrite={false} />
            </mesh>
            <Html portal={labelPortal} position={[cx, RACK_H + 0.35, y0 + 0.2]} center zIndexRange={[10, 0]} className="w3-label">
              <div className="w3-zone" style={{ color: "#334155" }}>
                RACK {r.id}
              </div>
            </Html>
          </group>
        );
      })}
      {/* SKU markers for bins an open order still needs */}
      {inventory.map((s) => (
        <Html portal={labelPortal} key={s.sku} position={[s.cell[0] + 0.5, SHELF_Y[SKU_LEVEL] + 0.75, s.cell[1] + 0.5]} center zIndexRange={[20, 10]} className="w3-label">
          <div
            className="w3-badge"
            style={{ background: s.stock === 0 ? C.bad : C.amber, fontSize: 9, padding: "1px 5px", display: needed.has(s.sku) || s.stock === 0 ? "block" : "none" }}
          >
            {s.sku}
          </div>
        </Html>
      ))}
    </group>
  );
}
