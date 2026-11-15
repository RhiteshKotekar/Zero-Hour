"use client";

// /replays — Material 3 Replays & Recorded Mission Sessions
// Allows loading the bundled judge demo and backend-saved simulation runs.
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as api from "@/lib/api";
import { OfflineNote } from "@/components/live/SessionDrawer";
import { DEFAULT_REPLAY, switchToReplay, useLive } from "@/lib/live";
import { useStore } from "@/lib/store";

export default function ReplaysPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<api.RunInfo[] | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [name, setName] = useState("");
  const mode = useStore((s) => s.mode);
  const attached = useLive((s) => s.attached);

  const theme = useStore((s) => s.theme);
  const toggleTheme = useStore((s) => s.toggleTheme);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.classList.toggle("dark", theme === "dark");
    }
  }, [theme]);

  const refresh = () =>
    Promise.all([api.listRuns(), api.getSession()])
      .then(([r]) => {
        setRuns([...r].sort((a, b) => String(b.saved_at ?? "").localeCompare(String(a.saved_at ?? ""))));
        setOnline(true);
      })
      .catch(() => setOnline(false));
  useEffect(() => {
    void refresh();
  }, []);

  const go = async (url: string, fn: () => Promise<void>) => {
    setMsg(null);
    try {
      await fn();
      router.push(`/?replay=${encodeURIComponent(url)}`);
    } catch (e) {
      setMsg((e as Error).message);
    }
  };

  const save = async () => {
    setMsg(null);
    try {
      const r = await api.saveRun(name || undefined);
      setMsg(`Saved ${r.id}`);
      setName("");
      await refresh();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };

  return (
    <main className="min-h-screen bg-bg text-ink p-6 transition-colors">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Top App Bar Header */}
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-3xl border border-line bg-panel p-5 shadow-sm">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="flex items-center gap-2 rounded-2xl border border-line bg-panel2 px-4 py-2 text-sm font-bold text-ink hover:bg-panel transition-all active:scale-95 shadow-xs"
            >
              ← Mission Control
            </Link>
            <div>
              <h1 className="text-xl font-black tracking-tight text-ink">MISSION REPLAY REPOSITORY</h1>
              <div className="text-xs font-semibold text-muted">Recorded SAMG runs — full twin state and timeline playback</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-muted hidden sm:inline">
              Mode: <b className="text-ink">{mode === "live" && attached ? "LIVE Session" : "Replay"}</b>
            </span>

            {/* Dark Mode Toggle */}
            <button
              onClick={toggleTheme}
              className="flex h-10 w-10 items-center justify-center rounded-2xl border border-line bg-panel2 text-ink hover:bg-panel transition-all active:scale-95"
              title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            >
              {theme === "dark" ? (
                <svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              ) : (
                <svg className="h-5 w-5 text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              )}
            </button>
          </div>
        </header>

        {msg && (
          <div className="rounded-2xl border border-ok/40 bg-ok-bg p-4 text-xs font-bold text-ok">
            {msg}
          </div>
        )}

        {/* Bundled Demo Run Card */}
        <section className="rounded-3xl border border-line bg-panel p-6 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-black uppercase tracking-wider text-muted">
              Bundled Reference Simulation
            </span>
            <span className="rounded-full bg-accent-bg px-2.5 py-0.5 text-xs font-black text-accent border border-accent/25">
              JUDGE DEMO
            </span>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="max-w-xl">
              <h2 className="text-base font-black text-ink">Judge Demo · Full Multi-Agent SAMG Run</h2>
              <p className="mt-1 text-xs text-muted font-medium leading-relaxed">
                Includes aisle congestion, robot motor fault, and a Byzantine malicious report. Demonstrates LinUCB dynamic topology adaptation, CP-SAT allocation, and ACP assurance proofs.
              </p>
            </div>

            <button
              onClick={() => go(DEFAULT_REPLAY, () => switchToReplay(DEFAULT_REPLAY))}
              className="flex items-center gap-2 rounded-2xl bg-accent px-5 py-2.5 text-xs font-black text-white shadow-md hover:bg-accent-hover transition-all active:scale-95"
            >
              <span>Launch Demo Replay</span>
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          </div>
        </section>

        {/* Save Session Card */}
        <section className="rounded-3xl border border-line bg-panel p-6 shadow-sm">
          <div className="text-xs font-black uppercase tracking-wider text-muted mb-3">
            Snapshot Current Session
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <input
              className="flex-1 min-w-[240px] rounded-2xl border border-line bg-panel2 px-4 py-2.5 text-xs font-bold placeholder:text-muted focus:outline-none focus:border-accent"
              placeholder="Session name or tag (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button
              onClick={save}
              className="rounded-2xl border border-line bg-panel2 px-5 py-2.5 text-xs font-bold text-ink hover:bg-panel transition-all active:scale-95 shadow-2xs"
            >
              Save Simulation Run
            </button>
          </div>
        </section>

        {/* Saved Runs List */}
        <section className="rounded-3xl border border-line bg-panel p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="text-xs font-black uppercase tracking-wider text-muted">
              Saved Simulation Artifacts (artifacts/runs)
            </div>
            <button
              onClick={refresh}
              className="text-xs font-black text-accent hover:underline"
            >
              Refresh
            </button>
          </div>

          {online === false ? (
            <OfflineNote onRetry={refresh} />
          ) : runs == null ? (
            <div className="text-xs text-muted font-medium py-4 text-center">Loading recorded runs…</div>
          ) : runs.length === 0 ? (
            <div className="text-xs text-muted font-medium py-6 text-center">
              No saved runs found in backend directory. Run a live simulation and click &quot;Save Simulation Run&quot; above.
            </div>
          ) : (
            <div className="divide-y divide-line">
              {runs.map((r) => (
                <div key={r.id} className="py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-black text-ink">{(r.name as string) ?? r.id}</div>
                    <div className="text-xs text-muted font-medium mt-0.5">
                      {r.scenario} · {r.saved_at ? new Date(r.saved_at).toLocaleString() : "Recent"}
                    </div>
                  </div>

                  <button
                    onClick={() => go(`/api/runs/${encodeURIComponent(r.id)}`, () => api.loadRun(r.id).then((res) => useStore.getState().setState(res.state, { mode: "replay", source: `REPLAY · ${(r.name as string) ?? r.id}` })))}
                    className="rounded-xl border border-line bg-panel2 px-4 py-1.5 text-xs font-bold text-ink hover:bg-panel transition-all active:scale-95"
                  >
                    Load Run
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
