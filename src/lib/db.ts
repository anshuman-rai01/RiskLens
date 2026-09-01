/**
 * Repository layer — the client-side analogue of the FastAPI routers.
 * Every function resolves the acting user from the verified access token
 * (requireUserId) and scopes all reads/writes to that id. Isolation is enforced
 * here, at query level — the UI never receives another user's row.
 */

import { ApiError, requireUserId } from "./auth";
import { CATEGORIES } from "./categories";
import { buildSampleEntries } from "./seed";
import { readTable, uid, writeTable } from "./store";
import { isNonNegativeNum, isValidDate, notFarFuture } from "./validation";
import type { Category, Entry, EntryData, Profile, UserRole } from "./types";

const readEntries = () => readTable<Entry>("entries");
const writeEntries = (rows: Entry[]) => writeTable("entries", rows);
const readProfiles = () => readTable<Profile>("profiles");
const writeProfiles = (rows: Profile[]) => writeTable("profiles", rows);

function assertOwn(entry: Entry | undefined, userId: string): Entry {
  // Belt-and-braces: even a forged id can't cross the ownership boundary.
  if (!entry || entry.userId !== userId) throw new ApiError("NOT_FOUND", "Entry not found.");
  return entry;
}

/* ---------------- entry validation (schema-driven) ---------------- */

export function validateEntryPayload(
  category: Category,
  raw: Record<string, unknown>,
  occurredOn: string,
): { errors: Record<string, string>; data: EntryData } {
  const meta = CATEGORIES[category];
  const errors: Record<string, string> = {};
  if (!isValidDate(occurredOn)) errors.occurredOn = "Enter a valid date.";
  else if (!notFarFuture(occurredOn, 1)) errors.occurredOn = "Date can't be more than a year ahead.";

  const clean: Record<string, unknown> = {};
  for (const f of meta.fields) {
    const v = raw[f.key];
    if (f.type === "number") {
      const num = typeof v === "number" ? v : v === "" || v == null ? NaN : Number(v);
      if (!Number.isFinite(num)) {
        if (f.required) errors[f.key] = `${f.label} must be a number.`;
        continue;
      }
      if (f.min != null && num < f.min) {
        errors[f.key] = `Minimum is ${f.min}.`;
        continue;
      }
      if (f.max != null && num > f.max) {
        errors[f.key] = `Maximum is ${f.max}.`;
        continue;
      }
      clean[f.key] = Math.round(num * 100) / 100;
    } else if (f.type === "select") {
      if (!(f.options ?? []).some((o) => o.value === v)) {
        errors[f.key] = `Choose a valid ${f.label.toLowerCase()}.`;
        continue;
      }
      clean[f.key] = v;
    } else if (f.type === "toggle") {
      clean[f.key] = v === true || v === "true";
    } else if (f.type === "date") {
      if (v == null || v === "") {
        clean[f.key] = null;
        continue;
      }
      const s = String(v);
      if (!isValidDate(s) || !notFarFuture(s, 10)) {
        errors[f.key] = "Enter a valid date.";
        continue;
      }
      clean[f.key] = s;
    } else {
      const s = typeof v === "string" ? v.trim() : "";
      if (!s && f.required) {
        errors[f.key] = `${f.label} is required.`;
        continue;
      }
      if (s.length > 80) {
        errors[f.key] = `Keep ${f.label.toLowerCase()} under 80 characters.`;
        continue;
      }
      clean[f.key] = s;
    }
  }
  return { errors, data: clean as unknown as EntryData };
}

/* ---------------- entries CRUD ---------------- */

export async function listEntries(category?: Category): Promise<Entry[]> {
  const me = await requireUserId();
  return readEntries()
    .filter((e) => e.userId === me && (!category || e.category === category))
    .sort((a, b) => b.occurredOn.localeCompare(a.occurredOn) || b.createdAt.localeCompare(a.createdAt));
}

export async function getEntry(id: string): Promise<Entry> {
  const me = await requireUserId();
  return assertOwn(readEntries().find((e) => e.id === id), me);
}

export async function createEntry(
  category: Category,
  raw: Record<string, unknown>,
  occurredOn: string,
  note: string,
): Promise<Entry> {
  const me = await requireUserId();
  const { errors, data } = validateEntryPayload(category, raw, occurredOn);
  const firstErr = Object.values(errors)[0];
  if (firstErr) throw new ApiError("VALIDATION", firstErr);
  const now = new Date().toISOString();
  const entry: Entry = {
    id: uid("ent"),
    userId: me,
    category,
    data,
    occurredOn,
    note: (note ?? "").trim().slice(0, 200),
    createdAt: now,
    updatedAt: now,
    revisions: [],
    derived: null,
  };
  writeEntries([...readEntries(), entry]);
  return entry;
}

export async function updateEntry(
  id: string,
  raw: Record<string, unknown>,
  occurredOn: string,
  note: string,
): Promise<Entry> {
  const me = await requireUserId();
  const rows = readEntries();
  const existing = assertOwn(rows.find((e) => e.id === id), me);
  const { errors, data } = validateEntryPayload(existing.category, raw, occurredOn);
  const firstErr = Object.values(errors)[0];
  if (firstErr) throw new ApiError("VALIDATION", firstErr);

  // History is append-only: the pre-edit state becomes a revision. Never overwritten.
  const revision = {
    data: existing.data,
    occurredOn: existing.occurredOn,
    note: existing.note,
    archivedAt: new Date().toISOString(),
  };
  const updated: Entry = {
    ...existing,
    data,
    occurredOn,
    note: (note ?? "").trim().slice(0, 200),
    updatedAt: new Date().toISOString(),
    revisions: [...existing.revisions, revision].slice(-24),
  };
  writeEntries(rows.map((e) => (e.id === id ? updated : e)));
  return updated;
}

export async function deleteEntry(id: string): Promise<void> {
  const me = await requireUserId();
  const rows = readEntries();
  assertOwn(rows.find((e) => e.id === id), me);
  writeEntries(rows.filter((e) => e.id !== id));
}

/* ---------------- profile ---------------- */

export async function getProfile(): Promise<Profile> {
  const me = await requireUserId();
  const p = readProfiles().find((x) => x.userId === me);
  if (!p) throw new ApiError("NOT_FOUND", "Profile not found.");
  return p;
}

export interface ProfilePatch {
  name: string;
  age: string | null;
  role: UserRole;
  currency: string;
  monthlySpendingCap: string | null;
  monthlySavingsTarget: string | null;
  weeklyStudyHours: string | null;
  weeklyFitnessMinutes: string | null;
  weeklyHabitCompletions: string | null;
}

function parseLimit(v: string | null, label: string): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (!isNonNegativeNum(n) || n > 10_000_000) throw new ApiError("VALIDATION", `${label} must be 0 or a positive number.`);
  return Math.round(n * 100) / 100;
}

export async function updateProfile(patch: ProfilePatch): Promise<Profile> {
  const me = await requireUserId();
  const name = patch.name.trim();
  if (!name) throw new ApiError("VALIDATION", "Name is required.", "name");
  if (name.length > 60) throw new ApiError("VALIDATION", "Keep the name under 60 characters.", "name");
  let age: number | null = null;
  if (patch.age != null && patch.age !== "") {
    age = Number(patch.age);
    if (!Number.isInteger(age) || age < 10 || age > 100) throw new ApiError("VALIDATION", "Age must be between 10 and 100.", "age");
  }
  const currency = patch.currency.trim() || "$";
  if (currency.length > 4) throw new ApiError("VALIDATION", "Currency must be a short symbol.", "currency");
  const roles: UserRole[] = ["student", "professional", "freelancer", "other"];
  if (!roles.includes(patch.role)) throw new ApiError("VALIDATION", "Pick a valid role.", "role");

  const next: Profile = {
    userId: me,
    name,
    age,
    role: patch.role,
    currency: currency.slice(0, 4),
    monthlySpendingCap: parseLimit(patch.monthlySpendingCap, "Spending cap"),
    monthlySavingsTarget: parseLimit(patch.monthlySavingsTarget, "Savings target"),
    weeklyStudyHours: parseLimit(patch.weeklyStudyHours, "Study target"),
    weeklyFitnessMinutes: parseLimit(patch.weeklyFitnessMinutes, "Fitness target"),
    weeklyHabitCompletions: parseLimit(patch.weeklyHabitCompletions, "Habit target"),
    updatedAt: new Date().toISOString(),
  };
  const rows = readProfiles();
  const exists = rows.some((p) => p.userId === me);
  writeProfiles(exists ? rows.map((p) => (p.userId === me ? next : p)) : [...rows, next]);
  return next;
}

/* ---------------- aggregates (plain arithmetic — the Milestone-2 model layer sits above this) ---------------- */

export interface Overview {
  monthSpent: number;
  monthIncome: number;
  monthSaved: number;
  studyHours7: number;
  fitnessMin7: number;
  habitHits7: number;
  counts: Record<Category, number>;
  totalEntries: number;
  entries7: number;
  recent: Entry[];
  goals: Entry[];
  memberSince: string;
}

export function monthKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export async function getOverview(): Promise<Overview> {
  const me = await requireUserId();
  const all = readEntries().filter((e) => e.userId === me);
  const now = new Date();
  const mk = monthKey(now);
  const cutoff7 = new Date(now.getTime() - 7 * 86_400_000).toISOString().slice(0, 10);

  const counts = {
    income_expense: 0,
    savings: 0,
    study: 0,
    academic: 0,
    fitness: 0,
    habits: 0,
    goals: 0,
  } as Record<Category, number>;
  let monthSpent = 0;
  let monthIncome = 0;
  let monthSaved = 0;
  let studyHours7 = 0;
  let fitnessMin7 = 0;
  let habitHits7 = 0;
  let entries7 = 0;

  for (const e of all) {
    counts[e.category] += 1;
    if (e.occurredOn >= cutoff7) entries7 += 1;
    const inMonth = e.occurredOn.slice(0, 7) === mk;
    if (e.category === "income_expense") {
      const d = e.data as { kind: string; amount: number };
      if (inMonth) {
        if (d.kind === "expense") monthSpent += d.amount;
        else monthIncome += d.amount;
      }
    } else if (e.category === "savings" && inMonth) {
      monthSaved += (e.data as { amount: number }).amount;
    } else if (e.category === "study" && e.occurredOn >= cutoff7) {
      studyHours7 += (e.data as { hours: number }).hours;
    } else if (e.category === "fitness" && e.occurredOn >= cutoff7) {
      fitnessMin7 += (e.data as { minutes: number }).minutes;
    } else if (e.category === "habits" && e.occurredOn >= cutoff7) {
      if ((e.data as { completed: boolean }).completed) habitHits7 += 1;
    }
  }

  const recent = [...all]
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .slice(0, 9);
  const goals = all
    .filter((e) => e.category === "goals")
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));

  const profile = readProfiles().find((p) => p.userId === me);
  return {
    monthSpent: Math.round(monthSpent * 100) / 100,
    monthIncome: Math.round(monthIncome * 100) / 100,
    monthSaved: Math.round(monthSaved * 100) / 100,
    studyHours7: Math.round(studyHours7 * 4) / 4,
    fitnessMin7: Math.round(fitnessMin7),
    habitHits7,
    counts,
    totalEntries: all.length,
    entries7,
    recent,
    goals,
    memberSince: profile?.updatedAt ?? new Date().toISOString(),
  };
}

export async function generateSampleEntries(): Promise<number> {
  const me = await requireUserId();
  const sample = buildSampleEntries(me);
  writeEntries([...readEntries(), ...sample]);
  return sample.length;
}
