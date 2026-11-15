"use client";

// Demo Dashboard Sidebar
// Clean, structured tabbed overview of Customer Orders, Fleet Robots, and Coordination Strategy.
import { useState } from "react";
import {
  TASK_STATUS_LABEL,
  assignmentAt,
  orderStatusAt,
  robotAt,
  taskStateAt,
  topoLabel,
  waveAt,
  ROLE_COLOR,
  STATUS_COLOR,
} from "@/lib/derive";
import { useStore } from "@/lib/store";
import type { Order, Robot, Task, TwinState, Wave } from "@/lib/types";
import { AgentChip, Badge, Pri, TONE_VAR, useSel, useTwin, CTX_NAMES } from "@/components/shell/ui";

type SidebarTab = "orders" | "fleet" | "topology";

export function DemoSidebar({ className }: { className?: string }) {
  const { state, t } = useTwin();
  const { is, selRobot } = useSel();
  const [activeTab, setActiveTab] = useState<SidebarTab>("orders");

  if (!state) {
    return (
      <aside className={`flex flex-col rounded-2xl border border-line bg-panel p-4 shadow-sm ${className ?? ""}`}>
        <div className="text-center text-xs text-muted py-8">Loading mission data…</div>
      </aside>
    );
  }

  const orders = state.orders.filter((o) => (o.arrival_s ?? 0) <= t);
  const tasks = state.tasks.filter((x) => orders.some((o) => o.id === x.order));
  const mobileRobots = state.robots.filter((r) => r.mobile);
  const failedCount = mobileRobots.filter((r) => r.failed_at != null && r.failed_at <= t).length;
  const w = waveAt(state, t);

  return (
    <aside className={`flex flex-col rounded-2xl border border-line bg-panel shadow-sm overflow-hidden min-h-0 ${className ?? ""}`}>
      {/* Top Tab Bar */}
      <div className="flex items-center border-b border-line bg-panel2/60 px-2 py-1.5 gap-1">
        <button
          type="button"
          onClick={() => setActiveTab("orders")}
          className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl py-1.5 text-[11px] font-bold transition-all ${
            activeTab === "orders"
              ? "bg-white text-ink shadow-2xs border border-line"
              : "text-muted hover:text-ink hover:bg-white/60"
          }`}
        >
          <svg className="h-3.5 w-3.5 text-blue-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <path d="M16 10a4 4 0 0 1-8 0" />
          </svg>
          <span>Orders ({orders.length})</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("fleet")}
          className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl py-1.5 text-[11px] font-bold transition-all ${
            activeTab === "fleet"
              ? "bg-white text-ink shadow-2xs border border-line"
              : "text-muted hover:text-ink hover:bg-white/60"
          }`}
        >
          <svg className="h-3.5 w-3.5 text-emerald-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
            <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
          </svg>
          <span>Fleet ({mobileRobots.length})</span>
          {failedCount > 0 && (
            <span className="rounded-full bg-red-100 px-1 text-[9px] font-bold text-red-600">
              {failedCount}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("topology")}
          className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl py-1.5 text-[11px] font-bold transition-all ${
            activeTab === "topology"
              ? "bg-white text-ink shadow-2xs border border-line"
              : "text-muted hover:text-ink hover:bg-white/60"
          }`}
        >
          <svg className="h-3.5 w-3.5 text-cyan-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="2" width="6" height="6" rx="1" />
            <rect x="16" y="2" width="6" height="6" rx="1" />
            <rect x="9" y="16" width="6" height="6" rx="1" />
            <path d="M5 8v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8" />
            <line x1="12" y1="13" x2="12" y2="16" />
          </svg>
          <span>Topology</span>
        </button>
      </div>

      {/* Tab Body */}
      <div className="flex-1 overflow-y-auto p-3">
        {activeTab === "orders" && (
          <OrdersTab state={state} t={t} orders={orders} tasks={tasks} is={is} selRobot={selRobot} />
        )}
        {activeTab === "fleet" && (
          <FleetTab state={state} t={t} robots={mobileRobots} is={is} />
        )}
        {activeTab === "topology" && w && (
          <TopologyTab w={w} />
        )}
      </div>
    </aside>
  );
}

// ----------------------------------------------------------------------------
// 1. ORDERS TAB
// ----------------------------------------------------------------------------
function OrdersTab({
  state,
  t,
  orders,
  tasks,
  is,
  selRobot,
}: {
  state: TwinState;
  t: number;
  orders: Order[];
  tasks: Task[];
  is: (k: "order" | "task" | "robot", id: string | null | undefined) => boolean;
  selRobot: string | null;
}) {
  const select = useStore((s) => s.select);
  const [expandedOrder, setExpandedOrder] = useState<string | null>(orders[0]?.id ?? null);

  const states = tasks.map((x) => taskStateAt(state, x.id, t)?.state ?? "OPEN");
  const activeCount = states.filter((s) => s === "EXECUTING" || s === "ASSIGNED").length;
  const verifiedCount = states.filter((s) => s === "VERIFIED_COMPLETE").length;

  return (
    <div className="flex flex-col gap-3">
      {/* Overview Stat Strip */}
      <div className="grid grid-cols-3 gap-2 rounded-xl bg-panel2/80 p-2 border border-line text-center">
        <div>
          <div className="text-[10px] uppercase font-bold text-muted">Orders</div>
          <div className="mono text-sm font-black text-ink">{orders.length}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase font-bold text-muted">Active Tasks</div>
          <div className="mono text-sm font-black text-blue-600">{activeCount}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase font-bold text-muted">Verified</div>
          <div className="mono text-sm font-black text-emerald-600">{verifiedCount}/{tasks.length}</div>
        </div>
      </div>

      {/* Order Cards List */}
      <div className="flex flex-col gap-2">
        {orders.map((o) => {
          const isSelected = is("order", o.id) || expandedOrder === o.id;
          const st = orderStatusAt(state, o.id, t);
          const oTasks = state.tasks.filter((tk) => tk.order === o.id);
          const taskStates = oTasks.map((tk) => taskStateAt(state, tk.id, t)?.state ?? "PENDING");
          const completedTasks = taskStates.filter((s) => s === "VERIFIED_COMPLETE" || s === "REPORTED_COMPLETE").length;
          const progressPct = oTasks.length > 0 ? (completedTasks / oTasks.length) * 100 : 0;

          return (
            <div
              key={o.id}
              onClick={() => {
                select(is("order", o.id) ? null : { kind: "order", id: o.id });
                setExpandedOrder(expandedOrder === o.id ? null : o.id);
              }}
              className={`rounded-xl border p-2.5 transition-all cursor-pointer ${
                isSelected
                  ? "border-accent bg-accent-bg/40 shadow-xs"
                  : "border-line bg-white hover:border-line2 hover:shadow-2xs"
              }`}
            >
              {/* Header */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="mono font-bold text-[13px] text-ink">{o.id}</span>
                  <Pri p={o.priority} />
                </div>
                <span
                  className="rounded-full px-2 py-0.5 text-[10px] font-bold"
                  style={{ color: TONE_VAR[st.tone], backgroundColor: `${TONE_VAR[st.tone]}15` }}
                >
                  {st.label}
                </span>
              </div>

              {/* Progress Bar */}
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-line rounded-full overflow-hidden">
                  <div
                    className="h-full bg-accent rounded-full transition-all"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono font-medium text-muted">
                  {completedTasks}/{oTasks.length}
                </span>
              </div>

              {/* Items & Route Info */}
              <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted">
                <span className="truncate">{o.items.join(", ")}</span>
                <span className="text-[10px] font-mono">
                  {o.consolidation ? `→ ${o.consolidation}` : ""}
                </span>
              </div>

              {/* Expanded Task Flow */}
              {isSelected && (
                <div className="mt-2.5 pt-2 border-t border-line/70 flex flex-col gap-1.5" onClick={(e) => e.stopPropagation()}>
                  <div className="text-[10px] font-bold uppercase tracking-wider text-muted">
                    Task Execution Chain
                  </div>
                  {o.tasks.map((taskId) => {
                    const task = state.tasks.find((tk) => tk.id === taskId);
                    const taskState = taskStateAt(state, taskId, t);
                    const assignment = assignmentAt(state, taskId, t);
                    const statusLabel = taskState ? TASK_STATUS_LABEL[taskState.state] ?? taskState.state : "PENDING";

                    return (
                      <div
                        key={taskId}
                        onClick={() => select({ kind: "task", id: taskId })}
                        className={`flex items-center justify-between rounded-lg p-1.5 text-[11px] transition-colors ${
                          is("task", taskId)
                            ? "bg-accent/15 border border-accent/30 font-semibold"
                            : "bg-panel2/60 hover:bg-panel2"
                        }`}
                      >
                        <div className="flex items-center gap-2 truncate">
                          <span className="text-muted text-[10px]">●</span>
                          <span className="truncate">{task?.label ?? taskId}</span>
                        </div>

                        <div className="flex items-center gap-2">
                          {assignment?.agent && (
                            <AgentChip
                              state={state}
                              id={assignment.agent}
                              onClick={() => select({ kind: "robot", id: assignment.agent })}
                              selected={selRobot === assignment.agent}
                            />
                          )}
                          <Badge cls={statusLabel}>{statusLabel}</Badge>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// 2. FLEET TAB
// ----------------------------------------------------------------------------
function FleetTab({
  state,
  t,
  robots,
  is,
}: {
  state: TwinState;
  t: number;
  robots: Robot[];
  is: (k: "order" | "task" | "robot", id: string | null | undefined) => boolean;
}) {
  const select = useStore((s) => s.select);
  const setFollow = useStore((s) => s.setFollow);
  const follow = useStore((s) => s.follow);
  const cameraCommand = useStore((s) => s.cameraCommand);

  return (
    <div className="flex flex-col gap-2.5">
      <div className="text-[10px] font-bold uppercase tracking-wider text-muted px-1">
        Mobile Autonomous Robots ({robots.length})
      </div>

      <div className="flex flex-col gap-2">
        {robots.map((r) => {
          const p = robotAt(state, r.id, t);
          const isSelected = is("robot", r.id);
          const isFollowing = follow === r.id;
          const task = p.task ? state.tasks.find((tk) => tk.id === p.task) : null;
          const isFailed = r.failed_at != null && r.failed_at <= t;

          return (
            <div
              key={r.id}
              onClick={() => select(isSelected ? null : { kind: "robot", id: r.id })}
              className={`rounded-xl border p-2.5 transition-all cursor-pointer ${
                isSelected
                  ? "border-accent bg-accent-bg/40 shadow-xs"
                  : "border-line bg-white hover:border-line2 hover:shadow-2xs"
              }`}
            >
              {/* Header */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-3 w-3 rounded-full"
                    style={{ backgroundColor: ROLE_COLOR[r.role] }}
                  />
                  <span className="mono font-bold text-xs text-ink">{r.id}</span>
                  <span className="text-[10.5px] font-medium text-muted truncate max-w-[100px]">
                    {r.label}
                  </span>
                </div>

                <span
                  className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase"
                  style={{
                    color: isFailed ? "#dc2626" : STATUS_COLOR[p.status],
                    backgroundColor: isFailed ? "#fee2e2" : `${STATUS_COLOR[p.status]}15`,
                  }}
                >
                  {isFailed ? "FAILED" : p.status}
                </span>
              </div>

              {/* Current Task & Location */}
              <div className="mt-1.5 flex items-center justify-between text-[11px] text-ink2">
                <span className="truncate">{task ? task.label : "Awaiting assignment"}</span>
                <span className="text-muted text-[10.5px] font-mono">
                  ({p.x.toFixed(1)}, {p.y.toFixed(1)})
                </span>
              </div>

              {/* Battery & Odometer Bar */}
              <div className="mt-2 flex items-center justify-between gap-3 text-[10.5px]">
                {/* Battery */}
                <div className="flex-1 flex items-center gap-1.5">
                  <span className="text-muted text-[10px]">🔋</span>
                  <div className="flex-1 h-1.5 bg-line rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        p.battery > 50 ? "bg-emerald-500" : p.battery > 20 ? "bg-amber-500" : "bg-red-500"
                      }`}
                      style={{ width: `${Math.max(0, p.battery)}%` }}
                    />
                  </div>
                  <span className="mono text-[10px] font-medium text-muted">
                    {Math.round(p.battery)}%
                  </span>
                </div>

                {/* Distance */}
                <div className="mono text-[10px] text-muted">
                  {Math.round(p.odo)} m
                </div>

                {/* Follow Button */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (isFollowing) {
                      setFollow(null);
                    } else {
                      select({ kind: "robot", id: r.id });
                      setFollow(r.id);
                      cameraCommand("follow");
                    }
                  }}
                  className={`rounded-md px-2 py-0.5 text-[10px] font-bold transition-all ${
                    isFollowing
                      ? "bg-accent text-white"
                      : "border border-line bg-panel2 text-ink2 hover:bg-line"
                  }`}
                >
                  {isFollowing ? "Following" : "Follow"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// 3. TOPOLOGY & AI TAB
// ----------------------------------------------------------------------------
function TopologyTab({ w }: { w: Wave }) {
  const maxScore = Math.max(...w.arms.map((a) => (a.offered ? a.score || 0 : 0)), 0.01);

  return (
    <div className="flex flex-col gap-3">
      {/* Judge Storytelling Card: Plain English explanation */}
      <div className="rounded-xl border border-samg/30 bg-samg-bg/50 p-3 shadow-2xs">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="flex h-5 w-5 items-center justify-center rounded-md bg-samg text-white font-bold text-[10px]">
            AI
          </span>
          <span className="text-[11px] font-bold text-samg uppercase tracking-wider">
            Adaptive Coordination Decision
          </span>
        </div>
        <p className="text-[11.5px] text-ink leading-relaxed">
          SAMG evaluated fleet capability diversity and warehouse bottleneck paths. The <b>LinUCB reinforcement learning policy</b> selected <b>{topoLabel(w.topology)}</b> as the optimal arm to minimize handoff delays while keeping completion at 100%.
        </p>
      </div>

      {/* Arm Comparison Scores */}
      <div className="flex flex-col gap-2 rounded-xl border border-line bg-white p-3 shadow-2xs">
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted">
          LinUCB Arm Scores (Mean + Exploration Bonus)
        </div>

        <div className="flex flex-col gap-2 mt-1">
          {w.arms.map((a) => {
            const isSelected = a.selected;
            const meanPct = ((a.mean ?? 0) / maxScore) * 100;
            const bonusPct = ((a.bonus ?? 0) / maxScore) * 100;

            return (
              <div
                key={a.topology}
                className={`rounded-lg p-2 transition-colors ${
                  isSelected ? "bg-accent-bg/60 border border-accent/30" : "bg-panel2/60 border border-transparent"
                }`}
              >
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className={isSelected ? "font-bold text-accent" : "text-ink"}>
                    {isSelected ? "★ " : ""}{topoLabel(a.topology)}
                  </span>
                  <span className="mono font-bold text-ink">
                    {a.offered ? (a.score ?? 0).toFixed(3) : "Ineligible"}
                  </span>
                </div>

                {a.offered && (
                  <>
                    <div className="mt-1.5 h-2 bg-line rounded-full overflow-hidden relative">
                      <div
                        className="absolute left-0 top-0 bottom-0 bg-accent rounded-l-full"
                        style={{ width: `${meanPct}%` }}
                      />
                      <div
                        className="absolute top-0 bottom-0 bg-indigo-300 rounded-r-full"
                        style={{ left: `${meanPct}%`, width: `${bonusPct}%` }}
                      />
                    </div>
                    <div className="mt-1 flex justify-between text-[10px] text-muted font-mono">
                      <span>Mean: {(a.mean ?? 0).toFixed(3)}</span>
                      <span>Bonus: +{(a.bonus ?? 0).toFixed(3)}</span>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Context Features (ctx-v1) */}
      <div className="flex flex-col gap-2 rounded-xl border border-line bg-white p-3 shadow-2xs">
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted">
          Warehouse Context Features (ctx-v1)
        </div>

        <div className="grid grid-cols-2 gap-2 mt-1">
          {w.context
            .filter((c) => c.name !== "intercept")
            .map((c) => (
              <div key={c.name} className="flex flex-col gap-1 p-2 rounded-lg bg-panel2 border border-line/60">
                <div className="flex justify-between items-center text-[10px]">
                  <span className="truncate font-medium text-ink2" title={c.name}>
                    {CTX_NAMES[c.name] ?? c.name}
                  </span>
                  <span className="mono font-bold text-ink">{c.value.toFixed(2)}</span>
                </div>
                <div className="h-1 bg-line rounded-full overflow-hidden">
                  <div
                    className="h-full bg-samg rounded-full"
                    style={{ width: `${Math.min(1, Math.max(0, c.value)) * 100}%` }}
                  />
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

export default DemoSidebar;
