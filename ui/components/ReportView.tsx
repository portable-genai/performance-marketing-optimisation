import type { PerformanceReport } from "@/lib/types";
import { CitationList } from "./CitationList";

const MARKET_LABEL: Record<string, string> = {
  JP: "Japan",
  AU: "Australia",
  SG: "Singapore",
};
const VERTICAL_LABEL: Record<string, string> = {
  banking: "Banking",
  online_retail: "Online retail",
};
const SEV_COLOR: Record<string, string> = {
  low: "bg-ink-100 text-ink-600",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-700",
  critical: "bg-red-100 text-red-700",
};
const VERDICT_LABEL: Record<string, string> = {
  ship: "SHIP",
  stop: "STOP",
  keep_running: "KEEP RUNNING",
};

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-4 rounded-xl border border-ink-200 bg-white shadow-panel">
      <h2 className="border-b border-ink-100 px-4 py-2.5 text-[13px] font-semibold text-ink-800">
        {title}
      </h2>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Bar({ value }: { value: number }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-28 overflow-hidden rounded-md border border-ink-200 bg-ink-100">
        <div
          className="h-full bg-gradient-to-r from-brand-500 to-brand-600"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-ink-500">{pct}%</span>
    </div>
  );
}

export function ReportView({ report }: { report: PerformanceReport }) {
  const eff = report.efficiency;
  const attr = report.attribution;
  const plan = report.budget_plan;
  const anomalies = report.anomalies;
  return (
    <div>
      <h1 className="text-lg font-semibold">Performance report — {report.account_id}</h1>
      <p className="mb-4 text-[13px] text-ink-500">
        <span className="mr-1.5 inline-block rounded-full border border-brand-100 bg-brand-50 px-2.5 py-0.5 text-[11px] font-semibold text-brand-700">
          {MARKET_LABEL[report.market] ?? report.market}
        </span>
        <span className="mr-1.5 inline-block rounded-full border border-brand-100 bg-brand-50 px-2.5 py-0.5 text-[11px] font-semibold text-brand-700">
          {VERTICAL_LABEL[report.vertical] ?? report.vertical}
        </span>
        id <b className="text-ink-800">{report.id}</b>
      </p>

      {report.requires_human_review ? (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
          HUMAN REVIEW REQUIRED — maker-checker gate. Do not move any budget until a qualified
          performance lead signs off.
        </div>
      ) : null}

      <Panel title="Summary">
        <p className="leading-relaxed">{report.summary}</p>
      </Panel>

      {eff ? (
        <Panel title="Channel efficiency (ROAS / CAC)">
          <div className="mb-2 text-xs text-ink-500">
            blended ROAS <b className="text-ink-800">{eff.blended_roas}</b> · blended CAC{" "}
            <b className="text-ink-800">{eff.blended_cac}</b>
          </div>
          {eff.channels.map((c, i) => (
            <div key={i} className="border-b border-ink-100 py-2 last:border-0">
              <div>
                <b>{c.channel}</b>{" "}
                <span className="text-xs text-ink-400">
                  spend {c.spend} · ROAS {c.roas} · CAC {c.cac}
                </span>
                {!(c.meets_roas_target && c.meets_cac_target) ? (
                  <span className="ml-2 rounded bg-orange-100 px-1.5 text-[11px] font-bold text-orange-700">
                    misses target
                  </span>
                ) : null}
              </div>
              <CitationList citations={c.citations} />
            </div>
          ))}
        </Panel>
      ) : null}

      {attr ? (
        <Panel title={`Attribution (${attr.model})`}>
          {attr.channels.length === 0 ? (
            <div className="text-xs text-ink-400">none</div>
          ) : (
            attr.channels.map((c, i) => (
              <div
                key={i}
                className="flex items-center gap-3 border-b border-ink-100 py-2 last:border-0"
              >
                <div className="flex-1">
                  {c.channel}{" "}
                  <span className="text-xs text-ink-400">
                    · {c.attributed_conversions} conv, {c.attributed_revenue} rev
                  </span>
                  <CitationList citations={c.citations} />
                </div>
                <Bar value={c.credit_share} />
              </div>
            ))
          )}
        </Panel>
      ) : null}

      {plan ? (
        <Panel title="Budget plan (deterministic, budget-neutral)">
          {plan.shifts.filter((s) => s.direction !== "hold").length === 0 ? (
            <div className="text-xs text-ink-400">no material shifts</div>
          ) : (
            plan.shifts
              .filter((s) => s.direction !== "hold")
              .map((s, i) => (
                <div key={i} className="flex gap-3 border-b border-ink-100 py-2 last:border-0">
                  <span
                    className={`h-fit rounded px-1.5 text-[11px] font-bold ${
                      SEV_COLOR[s.severity] ?? SEV_COLOR.medium
                    }`}
                  >
                    {s.severity}
                  </span>
                  <div className="flex-1">
                    <b>{s.channel}</b>{" "}
                    <span className="text-xs text-ink-400">{s.direction}</span> {s.delta}{" "}
                    <span className="text-xs text-ink-400">
                      ({s.current_budget} → {s.proposed_budget})
                    </span>
                    <CitationList citations={s.citations} />
                  </div>
                </div>
              ))
          )}
        </Panel>
      ) : null}

      {report.ab_results.length > 0 ? (
        <Panel title="A/B significance">
          {report.ab_results.map((r, i) => (
            <div key={i} className="flex gap-3 border-b border-ink-100 py-2 last:border-0">
              <div className="flex-1">
                <b>{r.test_id}</b>{" "}
                <span className="text-xs text-ink-400">
                  lift {(r.relative_lift * 100).toFixed(1)}%, p={r.p_value}
                </span>
                <CitationList citations={r.citations} />
              </div>
              <span className="h-fit rounded bg-brand-50 px-1.5 text-[11px] font-bold text-brand-700">
                {VERDICT_LABEL[r.verdict] ?? r.verdict}
              </span>
            </div>
          ))}
        </Panel>
      ) : null}

      {anomalies && anomalies.anomalies.length > 0 ? (
        <Panel title="Anomalies">
          {anomalies.anomalies.map((a, i) => (
            <div key={i} className="flex gap-3 border-b border-ink-100 py-2 last:border-0">
              <span
                className={`h-fit rounded px-1.5 text-[11px] font-bold ${
                  SEV_COLOR[a.severity] ?? SEV_COLOR.medium
                }`}
              >
                {a.severity}
              </span>
              <div className="flex-1">
                <b>{a.metric}</b>{" "}
                <span className="text-xs text-ink-400">
                  {a.kind}: {a.value} vs baseline {a.baseline} (z {a.deviation})
                </span>
                <CitationList citations={a.citations} />
              </div>
            </div>
          ))}
        </Panel>
      ) : null}
    </div>
  );
}
