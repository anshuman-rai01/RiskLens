import React, { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { CATEGORIES, fieldDefaults } from "../lib/categories";
import { formatCurrency, formatINR } from "../lib/currency";
import { createEntry, deleteEntry, listEntries, updateEntry, validateEntryPayload } from "../lib/db";
import { entrySummary } from "../lib/summary";
import type {
  AcademicData,
  Category,
  Entry,
  FitnessData,
  GoalData,
  HabitData,
  IncomeExpenseData,
  SavingsData,
  StudyData,
} from "../lib/types";
import { I } from "./icons";
import { Btn, Chip, EmptyState, Field, Input, Modal, Segmented, fmtDate, fmtTime, toast, todayISO, useDataVersion } from "./ui";

type Values = Record<string, string | number | boolean>;

function toFormValues(e: Entry): Values {
  const meta = CATEGORIES[e.category];
  const out: Values = {};
  for (const f of meta.fields) {
    const v = (e.data as unknown as Record<string, unknown>)[f.key];
    out[f.key] = v == null ? "" : typeof v === "boolean" ? String(v) : (v as string | number);
  }
  return out;
}

/* -------- per-category table cells -------- */

function headCells(cat: Category): string[] {
  switch (cat) {
    case "income_expense": return ["Type", "Description", "Amount"];
    case "savings": return ["Vault", "Amount"];
    case "study": return ["Subject", "Topic", "Hours"];
    case "academic": return ["Course", "Assessment", "Result"];
    case "fitness": return ["Activity", "Intensity", "Minutes"];
    case "habits": return ["Habit", "Status"];
    case "goals": return ["Goal", "Progress", "Deadline"];
  }
}

function bodyCells(e: Entry): ReactNode[] {
  switch (e.category) {
    case "income_expense": {
      const d = e.data as IncomeExpenseData;
      return [
        <Chip key="k" tone={d.kind === "income" ? "ok" : "neutral"}>{d.kind}</Chip>,
        <span key="l" className="font-medium text-ink">{d.label}</span>,
        <span key="a" className={`font-mono font-semibold tabular ${d.kind === "income" ? "text-ok" : "text-danger"}`}>
          {d.kind === "expense" ? "−" : "+"}{formatCurrency(d.amount)}
        </span>,
      ];
    }
    case "savings": {
      const d = e.data as SavingsData;
      return [
        <span key="v" className="font-medium text-ink">{d.vault}</span>,
        <span key="a" className="font-mono font-semibold tabular text-ok">+{formatCurrency(d.amount)}</span>,
      ];
    }
    case "study": {
      const d = e.data as StudyData;
      return [
        <span key="s" className="font-medium text-ink">{d.subject}</span>,
        <span key="t" className="text-ink-soft">{d.topic || "—"}</span>,
        <span key="h" className="font-mono tabular text-ink">{d.hours} h</span>,
      ];
    }
    case "academic": {
      const d = e.data as AcademicData;
      const pct = d.maxScore > 0 ? Math.round((d.score / d.maxScore) * 100) : 0;
      return [
        <span key="c" className="font-medium text-ink">{d.course}</span>,
        <span key="a" className="text-ink-soft">{d.assessment}</span>,
        <span key="s" className={`font-mono font-semibold tabular ${pct >= 50 ? "text-ink" : "text-danger"}`}>{d.score}/{d.maxScore} · {pct}%</span>,
      ];
    }
    case "fitness": {
      const d = e.data as FitnessData;
      return [
        <span key="a" className="font-medium text-ink">{d.activity}</span>,
        <Chip key="i" tone={d.intensity === "high" ? "danger" : d.intensity === "moderate" ? "warn" : "ok"}>{d.intensity}</Chip>,
        <span key="m" className="font-mono tabular text-ink">{d.minutes} min</span>,
      ];
    }
    case "habits": {
      const d = e.data as HabitData;
      return [
        <span key="h" className="font-medium text-ink">{d.habit}</span>,
        <Chip key="s" tone={d.completed ? "ok" : "danger"}>{d.completed ? "done" : "missed"}</Chip>,
      ];
    }
    case "goals": {
      const d = e.data as GoalData;
      const pct = d.target > 0 ? Math.round((d.current / d.target) * 100) : 0;
      return [
        <span key="t" className="font-medium text-ink">{d.title}</span>,
        <span key="p" className="font-mono tabular text-ink-soft">{formatINR(d.current)}/{formatINR(d.target)} {d.unit} · {pct}%</span>,
        <span key="d" className="font-mono tabular text-ink-soft">{d.deadline ? fmtDate(d.deadline) : "open"}</span>,
      ];
    }
  }
}

/* ================================================================ */

export function CategoryPage({ category }: { category: Category }) {
  const meta = CATEGORIES[category];
  const version = useDataVersion();
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [values, setValues] = useState<Values>(() => fieldDefaults(meta));
  const [occurredOn, setOccurredOn] = useState(todayISO());
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Entry | null>(null);
  const [detail, setDetail] = useState<Entry | null>(null);
  const [deleting, setDeleting] = useState<Entry | null>(null);
  const [filter, setFilter] = useState<"all" | "month" | "30d">("all");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let on = true;
    listEntries(category)
      .then((rows) => {
        if (on) setEntries(rows);
      })
      .catch(() => {});
    return () => {
      on = false;
    };
  }, [category, version]);

  // reset the form when switching categories
  useEffect(() => {
    setValues(fieldDefaults(meta));
    setOccurredOn(todayISO());
    setNote("");
    setErrors({});
    setEditing(null);
    setDetail(null);
    setFilter("all");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  const set = (key: string, v: string | number | boolean) => {
    setValues((prev) => ({ ...prev, [key]: v }));
    setErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const raw: Record<string, unknown> = { ...values };
    const check = validateEntryPayload(category, raw, occurredOn);
    if (Object.keys(check.errors).length > 0 || check.errors.occurredOn) {
      setErrors(check.errors);
      return;
    }
    setSubmitting(true);
    try {
      if (editing) {
        await updateEntry(editing.id, raw, occurredOn, note);
        toast("Entry updated — previous version archived as a revision.", "ok");
        setEditing(null);
      } else {
        await createEntry(category, raw, occurredOn, note);
        toast(`${meta.short} entry recorded.`, "ok");
      }
      setValues(fieldDefaults(meta));
      setOccurredOn(todayISO());
      setNote("");
      setErrors({});
    } catch (err) {
      toast(err instanceof Error ? err.message : "Save failed.", "err");
    } finally {
      setSubmitting(false);
    }
  };

  const startEdit = (entry: Entry) => {
    setEditing(entry);
    setValues(toFormValues(entry));
    setOccurredOn(entry.occurredOn);
    setNote(entry.note);
    setErrors({});
    setDetail(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    try {
      await deleteEntry(deleting.id);
      toast("Entry deleted.", "info");
      setDeleting(null);
      setDetail(null);
    } catch {
      toast("Delete failed.", "err");
    }
  };

  const filtered = (entries ?? []).filter((e) => {
    if (filter === "all") return true;
    const now = new Date();
    if (filter === "month") return e.occurredOn.slice(0, 7) === now.toISOString().slice(0, 7);
    const cutoff = new Date(now.getTime() - 30 * 86_400_000).toISOString().slice(0, 10);
    return e.occurredOn >= cutoff;
  });

  const heads = headCells(category);

  return (
    <div className="grid xl:grid-cols-[380px_1fr] gap-5 items-start">
      {/* ---------------- form ---------------- */}
      <section className="anim-rise rounded-xl border border-line bg-card shadow-sm overflow-hidden xl:sticky xl:top-[78px]">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-line" style={{ background: `${meta.accent}0d` }}>
          <span className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: `${meta.accent}1c`, color: meta.accent }}>
            <I name={meta.icon} size={18} />
          </span>
          <div className="flex-1 min-w-0">
            <h3 className="font-display font-semibold text-[15.5px] text-ink">
              {editing ? "Editing entry" : meta.verb}
            </h3>
            <p className="text-[11.5px] text-ink-faint truncate">
              {editing ? entrySummary(editing).text : meta.tagline}
            </p>
          </div>
          {editing && (
            <button
              onClick={() => {
                setEditing(null);
                setValues(fieldDefaults(meta));
                setOccurredOn(todayISO());
                setNote("");
                setErrors({});
              }}
              className="text-[12px] font-semibold text-ink-soft hover:text-danger transition-colors"
            >
              cancel
            </button>
          )}
        </div>

        <form onSubmit={submit} className="p-5 space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3.5">
            {meta.fields.map((f) => {
              const span = f.half ? "" : "col-span-2";
              const err = errors[f.key];
              if (f.type === "select" || f.type === "toggle") {
                return (
                  <div key={f.key} className={span}>
                    <Field label={f.label} error={err}>
                      <Segmented
                        options={f.options ?? []}
                        value={String(values[f.key] ?? f.defaultValue ?? "")}
                        onChange={(v) => set(f.key, v)}

                      />
                    </Field>
                  </div>
                );
              }
              return (
                <div key={f.key} className={span}>
                  <Field label={f.label} error={err} hint={f.suffix}>
                    <Input
                      type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                      placeholder={f.placeholder}
                      value={String(values[f.key] ?? "")}
                      invalid={!!err}
                      min={f.min}
                      max={f.max}
                      step={f.step}
                      onChange={(ev) => set(f.key, f.type === "number" ? ev.target.value : ev.target.value)}
                    />
                  </Field>
                </div>
              );
            })}
            <Field label="Date" error={errors.occurredOn}>
              <Input type="date" value={occurredOn} invalid={!!errors.occurredOn} max={todayISO()} onChange={(ev) => setOccurredOn(ev.target.value)} />
            </Field>
            <Field label="Note">
              <Input placeholder="optional context…" value={note} onChange={(ev) => setNote(ev.target.value)} maxLength={200} />
            </Field>
          </div>
          <Btn type="submit" loading={submitting} className="w-full py-2.5" style={{ background: meta.accent }}>
            <I name={editing ? "check" : "plus"} size={15} />
            {editing ? "Save changes" : `Add to ${meta.short.toLowerCase()}`}
          </Btn>
          <p className="font-mono text-[10.5px] text-ink-faint text-center">
            {editing ? "pre-edit values are archived, never overwritten" : "validated client-side and again in the repository"}
          </p>
        </form>
      </section>

      {/* ---------------- history ---------------- */}
      <section className="anim-rise stagger rounded-xl border border-line bg-card shadow-sm overflow-hidden min-w-0" style={{ "--i": 1 } as React.CSSProperties}>
        <div className="flex flex-wrap items-center gap-2.5 px-5 py-3.5 border-b border-line bg-bg-soft">
          <h3 className="font-display font-semibold text-[15.5px] text-ink mr-auto">
            History
            <span className="ml-2 font-mono text-[11.5px] font-normal text-ink-faint tabular">{filtered.length} records</span>
          </h3>
          {([["all", "All"], ["month", "This month"], ["30d", "30 days"]] as const).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className={`px-2.5 py-1 rounded-md text-[12px] font-semibold transition-colors focus-ring ${
                filter === k ? "bg-primary text-white" : "text-ink-soft hover:text-ink hover:bg-primary-soft"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {!entries ? (
          <div className="p-5 space-y-2.5">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="skeleton h-11 rounded-lg" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={meta.icon}
            title={entries.length === 0 ? `No ${meta.short.toLowerCase()} records yet` : "Nothing in this window"}
            body={
              entries.length === 0
                ? `Everything you log lands here with full history. Use the ${meta.verb.toLowerCase()} form — entries are retained forever and edits are archived as revisions.`
                : "Widen the filter to see older records."
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13.5px]">
              <thead>
                <tr className="text-left border-b border-line">
                  <th className="px-5 py-2.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-faint font-medium">Date</th>
                  {heads.map((h) => (
                    <th key={h} className="px-3 py-2.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-faint font-medium whitespace-nowrap">{h}</th>
                  ))}
                  <th className="px-3 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 60).map((e, i) => (
                  <tr
                    key={e.id}
                    className="reveal-row stagger group border-b border-line last:border-b-0 hover:bg-card/80 transition-colors cursor-pointer"
                    style={{ "--i": Math.min(i, 12) } as React.CSSProperties}
                    onClick={() => setDetail(e)}
                  >
                    <td className="px-5 py-2.5 font-mono text-[12px] text-ink-soft tabular whitespace-nowrap">{fmtDate(e.occurredOn)}</td>
                    {bodyCells(e).map((cell, ci) => (
                      <td key={ci} className="px-3 py-2.5 whitespace-nowrap max-w-[220px] truncate">{cell}</td>
                    ))}
                    <td className="px-3 py-2.5 whitespace-nowrap text-right">
                      <span className="inline-flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        {e.revisions.length > 0 && (
                          <span className="font-mono text-[10px] text-ink-faint mr-1" title={`${e.revisions.length} archived revision(s)`}>
                            v{e.revisions.length + 1}
                          </span>
                        )}
                        <button
                          onClick={(ev) => { ev.stopPropagation(); startEdit(e); }}
                          className="p-1.5 rounded-md text-ink-faint hover:text-primary hover:bg-primary-soft transition-colors focus-ring"
                          title="Edit (archives current version)"
                        >
                          <I name="pencil" size={14} />
                        </button>
                        <button
                          onClick={(ev) => { ev.stopPropagation(); setDeleting(e); }}
                          className="p-1.5 rounded-md text-ink-faint hover:text-danger hover:bg-danger-soft transition-colors focus-ring"
                          title="Delete"
                        >
                          <I name="trash" size={14} />
                        </button>
                        <I name="chevron" size={13} className="text-ink-faint" />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length > 60 && (
              <p className="px-5 py-3 text-center font-mono text-[11px] text-ink-faint">
                showing latest 60 of {filtered.length} — narrow the window to see more
              </p>
            )}
          </div>
        )}
      </section>

      {/* ---------------- detail / revisions drawer ---------------- */}
      {detail && (
        <div className="fixed inset-0 z-[60]">
          <button aria-label="Close details" className="absolute inset-0 bg-ink/40 backdrop-blur-[1px]" onClick={() => setDetail(null)} />
          <aside className="anim-slide-left absolute inset-y-0 right-0 w-full max-w-[400px] bg-card border-l border-line shadow-lg flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-line" style={{ background: `${meta.accent}0d` }}>
              <div className="flex items-center gap-2.5">
                <span style={{ color: meta.accent }}><I name={meta.icon} size={18} /></span>
                <h3 className="font-display font-semibold text-[15.5px] text-ink">Entry detail</h3>
              </div>
              <button onClick={() => setDetail(null)} className="p-1.5 rounded-md text-ink-faint hover:text-ink hover:bg-bg-soft transition-colors focus-ring">
                <I name="x" size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              <div>
                <p className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-ink-faint mb-2">Current · v{detail.revisions.length + 1}</p>
                <div className="rounded-lg border border-line bg-card px-4 py-3.5">
                  <p className="text-[15px] font-semibold text-ink">{entrySummary(detail).text}</p>
                  <p className="mt-1 font-mono text-[12.5px] text-ink-soft tabular">{entrySummary(detail).amount ?? ""}</p>
                  <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-ink-faint">
                    <span>date · {fmtDate(detail.occurredOn)}</span>
                    <span>created · {fmtDate(detail.createdAt)} {fmtTime(detail.createdAt)}</span>
                    {detail.note && <span>note · {detail.note}</span>}
                  </div>
                </div>
              </div>

              <div>
                <p className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-ink-faint mb-2 flex items-center gap-1.5">
                  <I name="history" size={12} />
                  Revision trail · {detail.revisions.length}
                </p>
                {detail.revisions.length === 0 ? (
                  <p className="text-[13px] text-ink-faint">No edits yet — the first edit archives this version here.</p>
                ) : (
                  <ol className="relative border-l-2 border-line ml-1.5 space-y-3.5">
                    {[...detail.revisions].reverse().map((r, i) => {
                      const revEntry = { ...detail, data: r.data } as Entry;
                      return (
                        <li key={i} className="ml-4">
                          <span className="absolute -left-[5px] mt-1.5 w-2 h-2 rounded-full bg-primary" />
                          <p className="text-[13px] font-medium text-ink">
                            v{detail.revisions.length - i} · {entrySummary(revEntry).text}
                          </p>
                          <p className="font-mono text-[11px] text-ink-soft tabular">
                            {entrySummary(revEntry).amount ?? ""} · archived {fmtDate(r.archivedAt)} {fmtTime(r.archivedAt)}
                          </p>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </div>
            </div>
            <div className="border-t border-line p-4 flex gap-2.5">
              <Btn variant="subtle" className="flex-1" onClick={() => startEdit(detail)}>
                <I name="pencil" size={14} />
                Edit
              </Btn>
              <Btn variant="danger" className="flex-1" onClick={() => setDeleting(detail)}>
                <I name="trash" size={14} />
                Delete
              </Btn>
            </div>
          </aside>
        </div>
      )}

      {/* ---------------- delete confirm ---------------- */}
      <Modal open={!!deleting} onClose={() => setDeleting(null)} title="Delete this entry?" width="max-w-md">
        {deleting && (
          <>
            <p className="text-[14px] text-ink-soft leading-relaxed">
              <span className="font-semibold text-ink">{entrySummary(deleting).text}</span>
              {" "}from {fmtDate(deleting.occurredOn)} will be permanently removed
              {deleting.revisions.length > 0 && (
                <> along with its <span className="font-semibold text-danger">{deleting.revisions.length} archived revision(s)</span></>
              )}
              . This can't be undone.
            </p>
            <div className="mt-5 flex gap-2.5 justify-end">
              <Btn variant="ghost" onClick={() => setDeleting(null)}>Keep it</Btn>
              <Btn variant="danger" onClick={confirmDelete}>
                <I name="trash" size={14} />
                Delete permanently
              </Btn>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}
