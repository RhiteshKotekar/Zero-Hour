"use client";
// /replays — recorded runs: the bundled judge demo + runs saved by the backend (artifacts/runs). Loading one puts
// the store in replay mode (browser clock) and returns to the control center.
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as api from "@/lib/api";
import { OfflineNote } from "@/components/live/SessionDrawer";
import { fmtS } from "@/lib/derive";
import { DEFAULT_REPLAY, loadSavedRun, switchToReplay, useLive } from "@/lib/live";
import { useStore } from "@/lib/store";

export default function ReplaysPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<api.RunInfo[] | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [hasSession, setHasSession] = useState(false);
  const mode = useStore((s) => s.mode);
  const attached = useLive((s) => s.attached);

  const refresh = () =>
    Promise.all([api.listRuns(), api.getSession()])
      .then(([r, s]) => {
        setRuns([...r].sort((a, b) => String(b.saved_at ?? "").localeCompare(String(a.saved_at ?? ""))));
        setHasSession(!!s.session_id);
        setOnline(true);
      })
      .catch(() => setOnline(false));
  useEffect(() => {
    void refresh();
  }, []);

  // the page shell loads `?replay=<url>` on mount (store.loadReplay also accepts a saved-run payload);
  // the store is updated here too so the run is shown even if the shell keeps the current state
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
    <main className="mx-auto max-w-[980px] p-4">
      <header className="flex flex-wrap items-center gap-3 rounded-[10px] border border-line bg-panel px-4 py-2.5">
        <Link href="/" className="btn">
          ← Control center
        </Link>
        <div>
          <h1 className="text-[14px] font-extrabold tracking-[0.12em]">REPLAYS</h1>
          <div className="text-[11px] text-muted">Recorded SAMG runs — the full backend state, revealed by time in the browser</div>
        </div>
        <span className="ml-auto text-[11px] text-muted">
          now showing: <b className="text-ink">{mode === "live" && attached ? "LIVE session" : "replay"}</b>
        </span>
      </header>

      <section className="mt-3 rounded-[10px] border border-line bg-panel p-3">
        <div className="cap">Bundled</div>
        <div className="mt-1.5 flex items-center gap-3">
          <div className="flex-1">
            <div className="font-semibold">Judge demo · recorded SAMG run</div>
            <div className="text-[11.5px] text-muted">
              Congestion, robot failure and a malicious report; produced by <code className="mono">build_state(run_warehouse(judge_demo))</code>. Works without the backend.
            </div>
          </div>
          <button className="btn primary" onClick={() => go(DEFAULT_REPLAY, () => switchToReplay(DEFAULT_REPLAY))}>
            Load
          </button>
        </div>
      </section>

      <section className="mt-3 rounded-[10px] border border-line bg-panel p-3">
        <div className="flex items-center gap-2">
          <div className="cap">Saved runs (backend · artifacts/runs)</div>
          <button className="ml-auto text-[11.5px] font-semibold text-accent" onClick={refresh}>
            refresh
          </button>
        </div>
        {online === false ? (
          <div className="mt-2">
            <OfflineNote onRetry={refresh} />
          </div>
        ) : runs == null ? (
          <div className="mt-2 text-[12px] text-muted">Loading…</div>
        ) : (
          <>
            <div className="mt-2 flex items-center gap-2 rounded-[7px] border border-line bg-panel2 p-2">
              <input
                className="flex-1 rounded-[6px] border border-line2 bg-white px-2 py-1 text-[12px]"
                placeholder="name (optional)"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <button className="btn" disabled={!hasSession} onClick={save} title={hasSession ? "" : "No live session on the server"}>
                Save current live run
              </button>
            </div>
            {runs.length === 0 && <div className="mt-2 text-[12px] text-muted">No saved runs yet.</div>}
            <table className="mt-2 w-full border-collapse text-[12px]">
              {runs.length > 0 && (
                <thead>
                  <tr className="border-b border-line text-left">
                    {["Run", "Scenario · policy · seed", "Sim time", "Waves", "Saved", ""].map((h) => (
                      <th key={h} className="py-1.5 pr-2">
                        <span className="cap">{h}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
              )}
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-b border-line last:border-0">
                    <td className="mono py-1.5 pr-2 font-semibold">{r.name ?? r.id}</td>
                    <td className="py-1.5 pr-2">
                      {r.scenario} · {r.policy} · <span className="mono">{r.seed}</span>
                    </td>
                    <td className="mono py-1.5 pr-2">
                      {fmtS(r.t ?? null)} {r.complete ? <span className="text-ok">complete</span> : <span className="text-warn">partial</span>}
                    </td>
                    <td className="mono py-1.5 pr-2">{r.waves ?? "—"}</td>
                    <td className="py-1.5 pr-2 text-muted">{String(r.saved_at ?? "—")}</td>
                    <td className="py-1.5 text-right">
                      <button className="btn" onClick={() => go(`${api.API_URL}/api/runs/${encodeURIComponent(r.id)}`, () => loadSavedRun(r.id))}>
                        Load
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {msg && <div className="mt-2 text-[12px] text-ink2">{msg}</div>}
      </section>
    </main>
  );
}
