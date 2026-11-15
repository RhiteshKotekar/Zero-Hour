"use client";
// Fleet (plan §6.6): status · task · battery · odometer per physical robot at t. Click = select (3D highlight),
// double-click = follow with the camera.
import { STATUS_COLOR, clockAt, robotAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { AgentChip, Badge, useSel, useTwin } from "@/components/shell/ui";

export interface FleetListProps {
  className?: string;
}

export function FleetList({ className }: FleetListProps) {
  const { state, t } = useTwin();
  const { selRobot } = useSel();
  const follow = useStore((s) => s.follow);
  if (!state) return <div className="zh-empty">Loading…</div>;
  const robots = state.robots.filter((r) => r.physical);
  return (
    <div className={`zh-scroll h-full ${className ?? ""}`}>
      <div className="zh-rb sticky top-0 z-[1] cursor-default bg-panel2 !py-1">
        <span className="cap">Robot</span>
        <span className="cap">Role</span>
        <span className="cap">Status · task</span>
        <span className="cap">Battery</span>
        <span className="cap text-right">Odometer</span>
      </div>
      {robots.map((r) => {
        const s = robotAt(state, r.id, t);
        const b = Math.max(0, s.battery);
        const failed = r.failed_at != null && r.failed_at <= t;
        return (
          <div
            key={r.id}
            className={`zh-rb ${selRobot === r.id ? "sel" : ""}`}
            onClick={() => useStore.getState().select({ kind: "robot", id: r.id })}
            onDoubleClick={() => {
              useStore.getState().select({ kind: "robot", id: r.id });
              useStore.getState().cameraCommand("follow");
            }}
            title="click: select · double-click: follow"
          >
            <AgentChip state={state} id={r.id} />
            <span className="truncate text-[10.5px] capitalize text-muted">{r.role}</span>
            <div className="flex min-w-0 items-center gap-1.5">
              <Badge cls={String(s.status)}>
                <span style={{ color: STATUS_COLOR[s.status] }}>●</span> {s.status}
              </Badge>
              <span className="mono truncate text-[10.5px] text-muted">{s.task ?? r.station ?? ""}</span>
              {failed && <span className="mono text-[10px] text-bad">down {clockAt(state, r.failed_at!)}</span>}
              {follow === r.id && <span className="text-[10px] font-bold text-accent">FOLLOWING</span>}
            </div>
            <div>
              <div className="zh-batt">
                <i style={{ width: `${b}%`, background: b < 20 ? "var(--bad)" : b < 45 ? "var(--warn)" : "var(--ok)" }} />
              </div>
              <span className="mono text-[10px] text-muted">{b.toFixed(1)}%</span>
            </div>
            <span className="mono text-right text-[11px]">{Math.round(s.odo)} m</span>
          </div>
        );
      })}
    </div>
  );
}

export default FleetList;
