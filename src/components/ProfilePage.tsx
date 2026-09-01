import React, { useEffect, useState, type FormEvent } from "react";
import { ApiError, listMySessions } from "../lib/auth";
import { getProfile, updateProfile, type ProfilePatch } from "../lib/db";
import { checkPassword } from "../lib/validation";
import type { Profile, SessionRecord } from "../lib/types";
import { useAuth } from "../state/AuthContext";
import { I } from "./icons";
import { Btn, Chip, Field, Input, Select, fmtDate, toast, useDataVersion } from "./ui";

const CURRENCIES = ["$", "€", "£", "₹", "¥", "₵", "R", "kr"];
const ROLES: Array<{ value: Profile["role"]; label: string }> = [
  { value: "student", label: "Student" },
  { value: "professional", label: "Professional" },
  { value: "freelancer", label: "Freelancer" },
  { value: "other", label: "Other" },
];

function SectionHead({ icon, title, sub }: { icon: string; title: string; sub: string }) {
  return (
    <div className="flex items-center gap-3 px-5 py-4 border-b border-line bg-card/60">
      <span className="w-9 h-9 rounded-lg bg-moss/12 text-moss flex items-center justify-center">
        <I name={icon} size={17} />
      </span>
      <div>
        <h3 className="font-display font-semibold text-[15.5px] text-ink leading-tight">{title}</h3>
        <p className="text-[12px] text-ink-faint">{sub}</p>
      </div>
    </div>
  );
}

export function ProfilePage() {
  const { user, changePassword, logoutEverywhere } = useAuth();
  const version = useDataVersion();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [form, setForm] = useState<ProfilePatch | null>(null);
  const [saving, setSaving] = useState(false);

  const [curPw, setCurPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [pwErr, setPwErr] = useState<{ cur?: string; next?: string }>({});
  const [changing, setChanging] = useState(false);
  const [sessions, setSessions] = useState<SessionRecord[]>([]);

  useEffect(() => {
    let on = true;
    getProfile()
      .then((p) => {
        if (!on) return;
        setProfile(p);
        setForm({
          name: p.name,
          age: p.age == null ? "" : String(p.age),
          role: p.role,
          currency: p.currency,
          monthlySpendingCap: p.monthlySpendingCap == null ? "" : String(p.monthlySpendingCap),
          monthlySavingsTarget: p.monthlySavingsTarget == null ? "" : String(p.monthlySavingsTarget),
          weeklyStudyHours: p.weeklyStudyHours == null ? "" : String(p.weeklyStudyHours),
          weeklyFitnessMinutes: p.weeklyFitnessMinutes == null ? "" : String(p.weeklyFitnessMinutes),
          weeklyHabitCompletions: p.weeklyHabitCompletions == null ? "" : String(p.weeklyHabitCompletions),
        });
      })
      .catch(() => {});
    return () => {
      on = false;
    };
  }, [version]);

  useEffect(() => {
    setSessions(listMySessions());
  }, [version]);

  const pwCheck = checkPassword(newPw);

  const saveProfile = async (e: FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    try {
      await updateProfile(form);
      toast("Profile & baselines saved.", "ok");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Save failed.", "err");
    } finally {
      setSaving(false);
    }
  };

  const doChangePw = async (e: FormEvent) => {
    e.preventDefault();
    const errs: { cur?: string; next?: string } = {};
    if (!curPw) errs.cur = "Enter your current password.";
    if (!pwCheck.ok) errs.next = pwCheck.message ?? "New password too weak.";
    setPwErr(errs);
    if (errs.cur || errs.next) return;
    setChanging(true);
    try {
      await changePassword(curPw, newPw);
      toast("Password updated — other sessions revoked.", "ok");
      setCurPw("");
      setNewPw("");
      setSessions(listMySessions());
    } catch (err) {
      if (err instanceof ApiError && err.field === "currentPassword") setPwErr({ cur: err.message });
      else toast(err instanceof Error ? err.message : "Change failed.", "err");
    } finally {
      setChanging(false);
    }
  };

  if (!profile || !form) {
    return (
      <div className="grid lg:grid-cols-2 gap-5">
        <div className="skeleton h-[380px] rounded-xl" />
        <div className="skeleton h-[380px] rounded-xl" />
      </div>
    );
  }

  const num = (v: string | null | undefined) => (v == null || v === "" ? null : String(v));

  return (
    <div className="grid lg:grid-cols-2 gap-5 items-start">
      {/* -------- identity & baselines -------- */}
      <form onSubmit={saveProfile} className="anim-rise rounded-xl border border-line bg-panel shadow-lift overflow-hidden" noValidate>
        <SectionHead icon="user" title="Identity" sub="who the console belongs to" />
        <div className="p-5 grid grid-cols-2 gap-3.5">
          <div className="col-span-2">
            <Field label="Full name">
              <Input value={form.name} placeholder="Amara Osei" onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
          </div>
          <Field label="Age">
            <Input type="number" min={10} max={100} value={form.age ?? ""} placeholder="22" onChange={(e) => setForm({ ...form, age: num(e.target.value) })} />
          </Field>
          <Field label="Role">
            <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Profile["role"] })}>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </Select>
          </Field>
          <Field label="Currency" hint="display symbol">
            <Select value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </Select>
          </Field>
          <div className="flex items-end pb-1.5">
            <p className="font-mono text-[11px] text-ink-faint leading-relaxed">
              member since<br />{user ? fmtDate(user.createdAt) : "—"}
            </p>
          </div>
        </div>

        <div className="px-5 py-3 border-y border-line bg-card/60">
          <h4 className="font-display font-semibold text-[14px] text-ink">Compliance baselines</h4>
          <p className="text-[12px] text-ink-faint mt-0.5">
            The limits <span className="font-semibold text-ink-soft">you</span> answer to. Leave blank to disable a baseline — the board adapts.
          </p>
        </div>
        <div className="p-5 grid grid-cols-2 gap-3.5">
          <Field label="Monthly spending cap" hint={profile.currency}>
            <Input type="number" min={0} step="0.01" placeholder="900" value={form.monthlySpendingCap ?? ""} onChange={(e) => setForm({ ...form, monthlySpendingCap: num(e.target.value) })} />
          </Field>
          <Field label="Monthly savings target" hint={profile.currency}>
            <Input type="number" min={0} step="0.01" placeholder="250" value={form.monthlySavingsTarget ?? ""} onChange={(e) => setForm({ ...form, monthlySavingsTarget: num(e.target.value) })} />
          </Field>
          <Field label="Weekly study hours" hint="h / week">
            <Input type="number" min={0} step="0.25" placeholder="14" value={form.weeklyStudyHours ?? ""} onChange={(e) => setForm({ ...form, weeklyStudyHours: num(e.target.value) })} />
          </Field>
          <Field label="Weekly fitness minutes" hint="min / week">
            <Input type="number" min={0} step="5" placeholder="150" value={form.weeklyFitnessMinutes ?? ""} onChange={(e) => setForm({ ...form, weeklyFitnessMinutes: num(e.target.value) })} />
          </Field>
          <Field label="Weekly habit completions" hint="count / week">
            <Input type="number" min={0} step="1" placeholder="12" value={form.weeklyHabitCompletions ?? ""} onChange={(e) => setForm({ ...form, weeklyHabitCompletions: num(e.target.value) })} />
          </Field>
          <div className="flex items-end">
            <Btn type="submit" loading={saving} className="w-full">
              <I name="check" size={15} />
              Save profile
            </Btn>
          </div>
        </div>
      </form>

      <div className="space-y-5">
        {/* -------- security -------- */}
        <form onSubmit={doChangePw} className="anim-rise stagger rounded-xl border border-line bg-panel shadow-lift overflow-hidden" style={{ "--i": 1 } as React.CSSProperties} noValidate>
          <SectionHead icon="key" title="Security" sub="rotate your password — other sessions are revoked" />
          <div className="p-5 space-y-4">
            <Field label="Current password" error={pwErr.cur}>
              <Input type="password" autoComplete="current-password" value={curPw} invalid={!!pwErr.cur} onChange={(e) => setCurPw(e.target.value)} />
            </Field>
            <Field label="New password" error={pwErr.next} hint="min 8 chars · letter + number">
              <Input type="password" autoComplete="new-password" value={newPw} invalid={!!pwErr.next} onChange={(e) => setNewPw(e.target.value)} />
            </Field>
            {newPw && (
              <div className="flex gap-1.5">
                {[1, 2, 3, 4].map((seg) => (
                  <div
                    key={seg}
                    className="h-1.5 flex-1 rounded-full transition-colors duration-300"
                    style={{
                      background:
                        pwCheck.score >= seg
                          ? pwCheck.score <= 1
                            ? "var(--color-coral)"
                            : pwCheck.score === 2
                              ? "var(--color-amber-bright)"
                              : "var(--color-moss-bright)"
                          : "var(--color-line)",
                    }}
                  />
                ))}
              </div>
            )}
            <Btn type="submit" variant="subtle" loading={changing} className="w-full">
              <I name="key" size={14} />
              Update password
            </Btn>
          </div>
        </form>

        {/* -------- sessions -------- */}
        <section className="anim-rise stagger rounded-xl border border-line bg-panel shadow-lift overflow-hidden" style={{ "--i": 2 } as React.CSSProperties}>
          <SectionHead icon="shield" title="Active sessions" sub="access 30 min · refresh 7 days, rotated on use" />
          <ul>
            {sessions.length === 0 && <li className="px-5 py-5 text-[13px] text-ink-faint">No active sessions.</li>}
            {sessions.map((s, i) => (
              <li key={s.jti} className="reveal-row stagger flex items-center gap-3 px-5 py-3 border-b border-line last:border-b-0" style={{ "--i": i } as React.CSSProperties}>
                <span className={`w-2 h-2 rounded-full shrink-0 ${i === 0 ? "bg-moss-bright" : "bg-line-strong"}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] font-medium text-ink truncate">
                    {i === 0 ? "This device" : s.userAgent.split(")")[0].replace("(", " · ") || "Other device"}
                  </p>
                  <p className="font-mono text-[10.5px] text-ink-faint">
                    jti {s.jti.slice(-8)} · rotated {fmtDate(s.rotatedAt)}
                  </p>
                </div>
                {i === 0 ? (
                  <Chip tone="ok">current</Chip>
                ) : (
                  <Chip tone="neutral">expires {fmtDate(s.expiresAt)}</Chip>
                )}
              </li>
            ))}
          </ul>
          <div className="p-4 border-t border-line">
            <Btn
              variant="danger"
              className="w-full"
              onClick={() => {
                void logoutEverywhere().then(() => toast("All sessions revoked.", "info"));
              }}
            >
              <I name="logout" size={14} />
              Sign out everywhere
            </Btn>
          </div>
        </section>
      </div>
    </div>
  );
}
