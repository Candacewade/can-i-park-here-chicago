import { useState } from "react";
import type { AnalyzeResponse } from "../types";

export function AgentInspector({ result }: { result: AnalyzeResponse }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card inspector">
      <button className="link" onClick={() => setOpen((o) => !o)}>
        {open ? "▾" : "▸"} Agent run inspector ({result.trace.length} tool calls
        {result.duration_ms ? `, ${(result.duration_ms / 1000).toFixed(1)}s` : ""})
      </button>
      {open && (
        <div className="inspector-body">
          <p className="meta">
            model {result.model} · run {result.run_id.slice(0, 8)} · deterministic
            core: {result.core_status ?? "—"}
          </p>
          <ol>
            {result.trace.map((t) => (
              <li key={t.order}>
                <div className="tc-head">
                  <code>{t.name}</code>
                  <span className={t.status === "error" ? "bad" : "ok"}>{t.status}</span>
                  {t.latency_ms != null && <span className="lat">{t.latency_ms.toFixed(0)}ms</span>}
                </div>
                <pre className="tc-args">{JSON.stringify(t.arguments)}</pre>
                <pre className="tc-res">{t.result_preview}</pre>
              </li>
            ))}
          </ol>
          {result.trace.length === 0 && (
            <p className="meta">
              The agent added no investigation — the deterministic core answered on its own.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
