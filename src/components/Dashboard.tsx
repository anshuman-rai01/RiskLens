import React, { useEffect, useState } from "react";
import type { Route } from "./AppShell";
import { CATEGORIES } from "../lib/categories";
import { generateSampleEntries, getOverview, getProfile, type Overview } from "../lib/db";
import { entrySummary } from "../lib/summary";
import type { Category, Entry, GoalData, Profile } from "../lib/types";
import { useAuth } from "../state/AuthContext";
import { I } from "./icons";
import { Bar, Btn, Chip, EmptyState, fmtDate, fmtMoney, fmtTime, toast, useDataVersion } from "./ui";

interface BaselineRow {
  key: string;
  icon: string;
  label: string;
  accent: string;
  usedText: string;
  pct: number;
  marker?: number;
  tone: "ok" | "warn" | "breach" | "unset";
  chipText: string;
  note: string;
}

function buildRows(p: Profile, o: Overview): BaselineRow[] {
  const c = p.currency;
  const now = new Date();
  const dayOfMonth = now.getDate();
  const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const elapsed = Math.min(1, Math.max(0.03, dayOfMonth / daysInMonth));
  const rows: BaselineRow[] = [];

  const push = (r: BaselineRow) => rows.push(r);

  if (p.monthlySpendingCap != null && p.monthlySpendingCap > 0) {
    const pct = (o.monthSpent / p.monthlySpendingCap) * 100;
    const projPct = pct / elapsed;
    push({
      key: "spend",
      icon: "wallet",
      label: "Monthly spending cap",
      accent: CATEGORIES.income_expense.accent,
      usedText: `${fmtMoney(o.monthSpent, c)} / ${fmtMoney(p.monthlySpendingCap, c)}`,
      pct,
      marker: elapsed * 100,
      tone: projPct > 100 ? "breach" : projPct > 90 ? "warn" : "ok",
      chipText: projPct > 100 ? "projected over" : projPct > 90 ? "running tight" : "within cap",
      note: `pace-adjusted ${Math.round(projPct)}% · marker = month elapsed`,
    });
  } else {
    push({ key: "spend", icon: "wallet", label: "Monthly spending cap", accent: CATEGORIES.income_expense.accent, usedText: "—", pct: 0, tone: "unset", chipText: "no baseline", note: "" });
  }

  if (p.monthlySavingsTarget != null && p.monthlySavingsTarget > 0) {
    const pct = (o.monthSaved / p.monthlySavingsTarget) * 100;
    const expected = p.monthlySavingsTarget * elapsed;
    const behind = o.monthSaved < expected * 0.75;
    push({
      key: "save",
      icon: "vault",
      label: "Monthly savings target",
      accent: CATEGORIES.savings.accent,
      usedText: `${fmtMoney(o.monthSaved, c)} / ${fmtMoney(p.monthlySavingsTarget, c)}`,
      pct,
      marker: elapsed * 100,
      tone: pct >= 100 ? "ok" : behind ? "warn" : "ok",
      chipText: pct >= 100 ? "target met" : behind ? "behind pace" : "on pace",
      note: "marker = expected share by today",
    });
  } else {
    push({ key: "save", icon: "vault", label: "Monthly savings target", accent: CATEGORIES.savings.accent, usedText: "—", pct: 0, tone: "unset", chipText: "no baseline", note: "" });
  }

  const weekly = (
    key: string,
    icon: string,
    label: string,
    cat: Category,
    used: number,
    target: number | null,
    unit: string,
  ) => {
    if (target != null && target > 0) {
      const pct = (used / target) * 100;
      push({
        key,
        icon,
        label,
        accent: CATEGORIES[cat].accent,
        usedText: `${used} / ${target} ${unit}`,
        pct,
        tone: pct >= 85 ? "ok" : pct >= 55 ? "warn" : "breach",
        chipText: pct >= 85 ? "on track" : pct >= 55 ? "behind" : "well behind",
        note: "rolling last 7 days",
      });
    } else {
      push({ key, icon, label, accent: CATEGORIES[cat].accent, usedText: "—", pct: 0, tone: "unset", chipText: "no baseline", note: "" });
    }
  };

  weekly("study", "book", "Weekly study hours", "study", o.studyHours7, p.weeklyStudyHours, "h");
  weekly("fitness", "pulse", "Weekly fitness minutes", "fitness", o.fitnessMin7, p.weeklyFitnessMinutes, "min");
  weekly("habits", "check", "Weekly habit completions", "habits", o.habitHits7, p.weeklyHabitCompletions, "done");

  return rows;
}

const toneChip = (t: BaselineRow["tone"]) => (t === "ok" ? "ok" : t === "warn" ? "warn" : t === "breach" ? "breach" : "neutral") as "ok" | "warn" | "breach" | "neutral";

export function Dashboard({ onNavigate }: { onNavigate: (r: Route) => void }) {
  const { user } = useAuth();
  const version = useDataVersion();
  const [data, setData] = useState<{ profile: Profile; overview: Overview } | null>(null);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    let on = true;
    Promise.all([getProfile(), getOverview()])
      .then(([profile, overview]) => {
        if (on) setData({ profile, overview });
      })
      .catch(() => {});
    return () => {
      on = false;
    };
  }, [version]);

  if (!data) {
    return (
      <div className="space-y-5">
        <div className="skeleton h-16 rounded-xl" />
        <div className="grid lg:grid-cols-[1fr_330px] gap-5">
          <div className="skeleton h-[380px] rounded-xl" />
          <div className="skeleton h-[380px] rounded-xl" />
        </div>
      </div>
    );
  }

  const { profile: p, overview: o } = data;
  const rows = buildRows(p, o);
  const firstName = (p.name || user?.email?.split("@")[0] || "operator").split(" ")[0];
  const hour = new Date().getHours();
  const greeting = hour < 5 ? "Still up" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const net = o.monthIncome - o.monthSpent;

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="anim-rise flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display font-bold text-[26px] sm:text-[30px] tracking-tight text-ink leading-tight">
            {greeting}, {firstName}.
          </h2>
          <p className="mt-1 text-[13.5px] text-ink-soft">
            {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })} · your
            signals against your own limits.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Chip tone="pine">
            <span className="relative flex w-1.5 h-1.5">
              <span className="absolute inline-flex w-full h-full rounded-full bg-amber-bright" style={{ animation: "rl-ping 2s cubic-bezier(0,0,0.2,1) infinite" }} />
              <span className="relative inline-flex w-1.5 h-1.5 rounded-full bg-amber-bright" />
            </span>
            7 sources live
          </Chip>
          <Chip tone="neutral" className="font-mono">
            {o.entries7} entries · 7d
          </Chip>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1fr_330px] gap-5 items-start">
        {/* ------- left column ------- */}
        <div className="space-y-5 min-w-0">
          {/* compliance board */}
          <section className="anim-rise stagger rounded-xl border border-line bg-panel shadow-lift overflow-hidden" style={{ "--i": 1 } as React.CSSProperties}>
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-line bg-card/60">
              <div className="flex items-center gap-2">
                <I name="shield" size={16} className="text-moss" />
                <h3 className="font-display font-semibold text-[15.5px] text-ink">Compliance board</h3>
              </div>
              <span className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-ink-faint">self-set baselines</span>
            </div>

            {o.totalEntries === 0 ? (
              <EmptyState
                icon="spark"
                title="No signals yet"
                body="Your compliance board compares live data against the baselines you define. Seed a realistic 60-day history to explore, or log your first entry."
                action={
                  <div className="flex flex-wrap gap-2.5 justify-center">
                    <Btn
                      loading={generating}
                      onClick={() => {
                        setGenerating(true);
                        generateSampleEntries()
                          .then((n) => toast(`${n} sample entries generated.`, "ok"))
                          .catch(() => toast("Could not generate sample data.", "err"))
                          .finally(() => setGenerating(false));
                      }}
                    >
                      <I name="spark" size={15} />
                      Generate sample history
                    </Btn>
                    <Btn variant="subtle" onClick={() => onNavigate({ view: "category", id: "income_expense" })}>
                      Log first entry
                    </Btn>
                  </div>
                }
              />
            ) : (
              <ul>
                {rows.map((r, i) => (
                  <li
                    key={r.key}
                    className="reveal-row stagger group flex items-center gap-4 px-5 py-3.5 border-b border-line last:border-b-0 hover:bg-card/70 transition-colors"
                    style={{ "--i": i + 1 } as React.CSSProperties}
                  >
                    <span
                      className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-transform duration-200 group-hover:scale-105"
                      style={{ background: `${r.accent}18`, color: r.accent }}
                    >
                      <I name={r.icon} size={17} />
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-baseline justify-between gap-3 mb-1.5">
                        <span className="text-[13.5px] font-semibold text-ink truncate">{r.label}</span>
                        <span className="font-mono text-[12.5px] text-ink-soft tabular shrink-0">{r.usedText}</span>
                      </div>
                      {r.tone === "unset" ? (
                        <div className="flex items-center gap-2">
                          <div className="h-2 flex-1 rounded-full border border-dashed border-line-strong" />
                          <button
                            onClick={() => onNavigate({ view: "profile" })}
                            className="text-[12px] font-semibold text-moss hover:text-pine underline decoration-moss/40 underline-offset-2 transition-colors"
                          >
                            set baseline →
                          </button>
                        </div>
                      ) : (
                        <Bar pct={r.pct} accent={r.accent} marker={r.marker} />
                      )}
                      {r.note && <p className="mt-1 font-mono text-[10.5px] text-ink-faint">{r.note}</p>}
                    </div>
                    <Chip tone={toneChip(r.tone)} className="w-[104px] justify-center shrink-0">
                      {r.chipText}
                    </Chip>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* recent activity */}
          <section className="anim-rise stagger rounded-xl border border-line bg-panel shadow-lift overflow-hidden" style={{ "--i": 2 } as React.CSSProperties}>
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-line bg-card/60">
              <div className="flex items-center gap-2">
                <I name="history" size={16} className="text-moss" />
                <h3 className="font-display font-semibold text-[15.5px] text-ink">Recent activity</h3>
              </div>
              <span className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-ink-faint">latest first</span>
            </div>
            {o.recent.length === 0 ? (
              <p className="px-5 py-8 text-center text-sm text-ink-faint">Nothing logged yet — entries appear here in real time.</p>
            ) : (
              <ul>
                {o.recent.map((e: Entry, i) => {
                  const meta = CATEGORIES[e.category];
                  const s = entrySummary(e, p.currency);
                  return (
                    <li
                      key={e.id}
                      className="reveal-row stagger flex items-center gap-3.5 px-5 py-[9px] border-b border-line last:border-b-0 hover:bg-card/70 cursor-pointer transition-colors"
                      style={{ "--i": i } as React.CSSProperties}
                      onClick={() => onNavigate({ view: "category", id: e.category })}
                    >
                      <span className="w-7 h-7 rounded-md flex items-center justify-center shrink-0" style={{ background: `${meta.accent}15`, color: meta.accent }}>
                        <I name={meta.icon} size={14} />
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-[13.5px] font-medium text-ink truncate">{s.text}</p>
                        <p className="font-mono text-[10.5px] text-ink-faint">
                          {meta.short.toLowerCase()} · {fmtDate(e.occurredOn)} {fmtTime(e.createdAt)}
                        </p>
                      </div>
                      {s.amount && (
                        <span className={`font-mono text-[12.5px] font-semibold tabular shrink-0 ${s.tone === "pos" ? "text-ok" : s.tone === "neg" ? "text-coral" : "text-ink-soft"}`}>
                          {s.amount}
                        </span>
                      )}
                      <I name="chevron" size={13} className="text-ink-faint shrink-0" />
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>

        {/* ------- right column ------- */}
        <div className="space-y-5">
          <section className="anim-rise stagger rounded-xl border border-line bg-pine-deep bg-console text-mint shadow-lift p-5" style={{ "--i": 2 } as React.CSSProperties}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display font-semibold text-[15px]">Month pulse</h3>
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-mint/40">
                {new Date().toLocaleDateString(undefined, { month: "short" })}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "net flow", value: fmtMoney(net, p.currency), tone: net >= 0 ? "#7fc79b" : "#e8a196" },
                { label: "saved", value: fmtMoney(o.monthSaved, p.currency), tone: "#e0a63c" },
                { label: "study · 7d", value: `${o.studyHours7} h`, tone: "#8fc3dd" },
                { label: "records", value: String(o.totalEntries), tone: "#d8e9dd" },
              ].map((s) => (
                <div key={s.label} className="rounded-lg border border-mint/10 bg-pine-ink/45 px-3.5 py-3 hover:border-mint/25 transition-colors">
                  <p className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-mint/45">{s.label}</p>
                  <p className="mt-1 font-mono font-semibold text-[17px] tabular leading-none" style={{ color: s.tone }}>
                    {s.value}
                  </p>
                </div>
              ))}
            </div>
            <p className="mt-4 font-mono text-[10.5px] text-mint/40 leading-relaxed">
              plain arithmetic for now — the predictive layer lands in milestone 2.
            </p>
          </section>

          <section className="anim-rise stagger rounded-xl border border-line bg-panel shadow-lift overflow-hidden" style={{ "--i": 3 } as React.CSSProperties}>
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-line bg-card/60">
              <div className="flex items-center gap-2">
                <I name="target" size={16} className="text-moss" />
                <h3 className="font-display font-semibold text-[15.5px] text-ink">Goals</h3>
              </div>
              <button
                onClick={() => onNavigate({ view: "category", id: "goals" })}
                className="text-[12px] font-semibold text-moss hover:text-pine transition-colors"
              >
                manage →
              </button>
            </div>
            {o.goals.length === 0 ? (
              <p className="px-5 py-7 text-center text-[13px] text-ink-faint">
                No goals yet. Set one — progress updates are kept as revision history.
              </p>
            ) : (
              <ul>
                {o.goals.slice(0, 4).map((g) => {
                  const d = g.data as GoalData;
                  const pct = d.target > 0 ? (d.current / d.target) * 100 : 0;
                  const days = d.deadline ? Math.ceil((new Date(d.deadline + "T12:00:00").getTime() - Date.now()) / 86_400_000) : null;
                  return (
                    <li key={g.id} className="px-5 py-3.5 border-b border-line last:border-b-0 hover:bg-card/70 transition-colors">
                      <div className="flex items-baseline justify-between gap-3 mb-1.5">
                        <span className="text-[13.5px] font-semibold text-ink truncate">{d.title}</span>
                        <span className="font-mono text-[11.5px] text-ink-soft tabular shrink-0">
                          {Math.round(pct)}%
                        </span>
                      </div>
                      <Bar pct={pct} accent={CATEGORIES.goals.accent} height={6} />
                      <div className="mt-1.5 flex items-center justify-between">
                        <span className="font-mono text-[10.5px] text-ink-faint">
                          {d.current.toLocaleString()}/{d.target.toLocaleString()} {d.unit}
                        </span>
                        {days != null && (
                          <Chip tone={days < 7 ? "breach" : days < 14 ? "warn" : "neutral"} className="!text-[10.5px]">
                            {days < 0 ? "overdue" : `${days}d left`}
                          </Chip>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
