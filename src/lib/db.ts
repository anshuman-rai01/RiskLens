/**
 * RiskLens Repository Layer — backed by FastAPI REST API
 * 
 * Replaces client-side localStorage/store.ts persistence with real endpoints:
 * - /entries (generic behavioral time-series categories)
 * - /goals (personal targets with computed progress and deadlines)
 * - /profile (user compliance baselines and preferences)
 */

import { ApiError, apiRequest } from "./api";
import { CATEGORIES } from "./categories";
import { CURRENCY_SYMBOL } from "./currency";
import { emitChange } from "./store";
import { isNonNegativeNum, isValidDate, notFarFuture } from "./validation";
import type {
  Category,
  Entry,
  EntryData,
  GoalData,
  IncomeExpenseData,
  Profile,
  SavingsData,
  StudyData,
  AcademicData,
  FitnessData,
  HabitData,
  UserRole,
} from "./types";

export { ApiError };

/* ---------------- backend response interfaces ---------------- */

interface BackendEntry {
  id: string;
  category: string;
  subcategory: string | null;
  value: number | string;
  unit: string | null;
  max_value?: number | string | null;
  occurred_at: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

interface BackendEntryList {
  items: BackendEntry[];
  total: number;
  limit: number;
  offset: number;
}

interface BackendGoal {
  id: string;
  name: string;
  target_value: number | string;
  current_value: number | string;
  unit: string | null;
  deadline: string | null;
  progress_percent: number;
  is_completed: boolean;
  created_at: string;
  updated_at: string;
}

interface BackendGoalList {
  items: BackendGoal[];
  total: number;
  limit: number;
  offset: number;
}

interface BackendProfile {
  user_id: string;
  name: string;
  age: number | null;
  role: string;
  currency: string;
  monthly_spending_cap: number | string | null;
  monthly_savings_target: number | string | null;
  weekly_study_hours: number | string | null;
  weekly_fitness_minutes: number | null;
  weekly_habit_completions: number | null;
  onboarded: boolean;
  updated_at: string;
}

/* ---------------- mappers ---------------- */

/** Categories whose backend `notes` column holds the user's free-text Note. */
const FREE_TEXT_NOTE_CATEGORIES = new Set<string>(["savings", "habits"]);

function mapBackendEntryToFrontend(b: BackendEntry): Entry {
  const val = Number(b.value) || 0;
  let data: EntryData;

  switch (b.category) {
    case "income_expense": {
      const isIncome = b.notes === "income" || b.unit === "income";
      data = {
        kind: isIncome ? "income" : "expense",
        amount: val,
        label: b.subcategory || (b.notes && b.notes !== "income" && b.notes !== "expense" ? b.notes : "Expense"),
      } as IncomeExpenseData;
      break;
    }
    case "savings": {
      data = {
        amount: val,
        vault: b.subcategory || "Savings",
      } as SavingsData;
      break;
    }
    case "study": {
      data = {
        subject: b.subcategory || "Study Session",
        hours: val,
        topic: b.notes || "",
      } as StudyData;
      break;
    }
    case "academic": {
      data = {
        course: b.subcategory || "Academics",
        assessment: b.notes || "Assessment",
        score: val,
        // Rows created before max_value existed were logged on a 0-100 scale.
        maxScore: b.max_value != null ? Number(b.max_value) : 100,
      } as AcademicData;
      break;
    }
    case "fitness": {
      const validIntensities = ["low", "moderate", "high"] as const;
      const intensity = validIntensities.includes(b.notes as any) ? (b.notes as "low" | "moderate" | "high") : "moderate";
      data = {
        activity: b.subcategory || "Workout",
        minutes: Math.round(val),
        intensity,
      } as FitnessData;
      break;
    }
    case "habits": {
      data = {
        habit: b.subcategory || "Daily Habit",
        completed: val >= 1.0,
      } as HabitData;
      break;
    }
    default: {
      data = {
        title: b.subcategory || "Goal",
        unit: b.unit || "units",
        target: 100,
        current: val,
        deadline: null,
      } as GoalData;
    }
  }

  return {
    id: b.id,
    userId: "current_user",
    category: b.category as Category,
    data,
    occurredOn: b.occurred_at,
    // For these categories the notes column stores a structured field (kind, topic,
    // assessment, intensity), not the free-text Note, so don't echo it back as one.
    note: FREE_TEXT_NOTE_CATEGORIES.has(b.category) ? b.notes || "" : "",
    createdAt: b.created_at,
    updatedAt: b.updated_at,
    revisions: [],
    derived: null,
  };
}

function mapBackendGoalToFrontend(g: BackendGoal): Entry {
  const target = Number(g.target_value) || 0;
  const current = Number(g.current_value) || 0;

  const data: GoalData = {
    title: g.name,
    unit: g.unit || "units",
    target,
    current,
    deadline: g.deadline,
  };

  return {
    id: g.id,
    userId: "current_user",
    category: "goals",
    data,
    occurredOn: g.created_at ? g.created_at.slice(0, 10) : new Date().toISOString().slice(0, 10),
    note: g.is_completed ? "Completed" : `${g.progress_percent}% completed`,
    createdAt: g.created_at,
    updatedAt: g.updated_at,
    revisions: [],
    derived: null,
  };
}

function mapFrontendToBackendEntryPayload(
  category: Category,
  raw: Record<string, unknown>,
  occurredOn: string,
  note: string
) {
  let subcategory: string | null = null;
  let value = 0;
  let unit: string | null = null;
  let maxValue: number | null = null;
  let notes = (note || "").trim();

  switch (category) {
    case "income_expense": {
      value = Number(raw.amount) || 0;
      unit = "INR";
      subcategory = String(raw.label || raw.kind || "Expense");
      notes = String(raw.kind || "expense");
      break;
    }
    case "savings": {
      value = Number(raw.amount) || 0;
      unit = "INR";
      subcategory = String(raw.vault || "Savings");
      break;
    }
    case "study": {
      value = Number(raw.hours) || 0;
      unit = "hours";
      subcategory = String(raw.subject || "Study");
      notes = String(raw.topic || note || "");
      break;
    }
    case "academic": {
      value = Number(raw.score) || 0;
      unit = "score";
      maxValue = Number(raw.maxScore) || null;
      subcategory = String(raw.course || "Academics");
      notes = String(raw.assessment || note || "");
      break;
    }
    case "fitness": {
      value = Number(raw.minutes) || 0;
      unit = "minutes";
      subcategory = String(raw.activity || "Activity");
      notes = String(raw.intensity || "moderate");
      break;
    }
    case "habits": {
      value = (raw.completed === true || raw.completed === "true") ? 1.0 : 0.0;
      unit = "count";
      subcategory = String(raw.habit || "Habit");
      break;
    }
  }

  return {
    category,
    subcategory: subcategory ? subcategory.slice(0, 200) : null,
    value,
    unit,
    max_value: maxValue,
    occurred_at: occurredOn,
    notes: notes ? notes.slice(0, 500) : null,
  };
}

/* ---------------- entry validation ---------------- */

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
  if (category === "academic" && !errors.score && !errors.maxScore) {
    const score = clean.score as number | undefined;
    const maxScore = clean.maxScore as number | undefined;
    if (score != null && maxScore != null && score > maxScore) {
      errors.score = "Obtained marks can't exceed maximum marks.";
    }
  }
  return { errors, data: clean as unknown as EntryData };
}

/* ---------------- entries & goals CRUD ---------------- */

export async function listEntries(category?: Category): Promise<Entry[]> {
  if (category === "goals") {
    const res = await apiRequest<BackendGoalList>("/goals?limit=200");
    return (res.items || []).map(mapBackendGoalToFrontend);
  }

  const query = category ? `?category=${category}&limit=200` : "?limit=200";
  const res = await apiRequest<BackendEntryList>(`/entries${query}`);
  return (res.items || []).map(mapBackendEntryToFrontend);
}

export async function getEntry(id: string): Promise<Entry> {
  try {
    const res = await apiRequest<BackendEntry>(`/entries/${id}`);
    return mapBackendEntryToFrontend(res);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      const g = await apiRequest<BackendGoal>(`/goals/${id}`);
      return mapBackendGoalToFrontend(g);
    }
    throw err;
  }
}

export async function createEntry(
  category: Category,
  raw: Record<string, unknown>,
  occurredOn: string,
  note: string,
): Promise<Entry> {
  if (category === "goals") {
    const name = String(raw.title || raw.name || "Goal").trim();
    const targetVal = Number(raw.target || raw.target_value) || 100;
    const currentVal = Number(raw.current || raw.current_value) || 0;
    const unit = String(raw.unit || "units").trim();
    const deadline = raw.deadline ? String(raw.deadline) : null;

    const res = await apiRequest<BackendGoal>("/goals", {
      method: "POST",
      body: JSON.stringify({
        title: name,
        target: targetVal,
        current: currentVal,
        unit,
        deadline,
      }),
    });
    emitChange();
    return mapBackendGoalToFrontend(res);
  }

  const payload = mapFrontendToBackendEntryPayload(category, raw, occurredOn, note);
  const res = await apiRequest<BackendEntry>("/entries", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  emitChange();
  return mapBackendEntryToFrontend(res);
}

export async function updateEntry(
  id: string,
  category: Category,
  raw: Record<string, unknown>,
  occurredOn: string,
  note: string,
): Promise<Entry> {
  if (category === "goals") {
    const updatePayload: Record<string, unknown> = {};
    if (raw.title !== undefined) updatePayload.title = String(raw.title).trim();
    if (raw.target !== undefined) updatePayload.target = Number(raw.target);
    if (raw.current !== undefined) updatePayload.current = Number(raw.current);
    if (raw.unit !== undefined) updatePayload.unit = String(raw.unit).trim();
    if (raw.deadline !== undefined) updatePayload.deadline = raw.deadline || null;

    const res = await apiRequest<BackendGoal>(`/goals/${id}`, {
      method: "PUT",
      body: JSON.stringify(updatePayload),
    });
    emitChange();
    return mapBackendGoalToFrontend(res);
  }

  // Build the body with the same mapper createEntry uses, so every field the form
  // shows (including those stored in subcategory/notes) is written back on edit.
  // `category` is immutable server-side and the endpoint rejects it, so strip it.
  const { category: _immutable, ...updateBody } = mapFrontendToBackendEntryPayload(
    category,
    raw,
    occurredOn,
    note,
  );

  const res = await apiRequest<BackendEntry>(`/entries/${id}`, {
    method: "PUT",
    body: JSON.stringify(updateBody),
  });
  emitChange();
  return mapBackendEntryToFrontend(res);
}

export async function deleteEntry(id: string): Promise<void> {
  try {
    await apiRequest(`/entries/${id}`, { method: "DELETE" });
    emitChange();
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      await apiRequest(`/goals/${id}`, { method: "DELETE" });
      emitChange();
      return;
    }
    throw err;
  }
}

/* ---------------- profile ---------------- */

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

function mapBackendProfileToFrontend(p: BackendProfile): Profile {
  return {
    userId: p.user_id,
    name: p.name || "",
    age: p.age,
    role: (p.role as UserRole) || "student",
    currency: CURRENCY_SYMBOL,
    monthlySpendingCap: p.monthly_spending_cap != null ? Number(p.monthly_spending_cap) : null,
    monthlySavingsTarget: p.monthly_savings_target != null ? Number(p.monthly_savings_target) : null,
    weeklyStudyHours: p.weekly_study_hours != null ? Number(p.weekly_study_hours) : null,
    weeklyFitnessMinutes: p.weekly_fitness_minutes != null ? Number(p.weekly_fitness_minutes) : null,
    weeklyHabitCompletions: p.weekly_habit_completions != null ? Number(p.weekly_habit_completions) : null,
    updatedAt: p.updated_at,
  };
}

export async function getProfile(): Promise<Profile> {
  const p = await apiRequest<BackendProfile>("/profile");
  return mapBackendProfileToFrontend(p);
}

export async function updateProfile(patch: ProfilePatch): Promise<Profile> {
  const name = patch.name.trim();
  if (!name) throw new ApiError("VALIDATION", "Name is required.", "name");
  if (name.length > 60) throw new ApiError("VALIDATION", "Keep the name under 60 characters.", "name");

  let age: number | null = null;
  if (patch.age != null && patch.age !== "") {
    age = Number(patch.age);
    if (!Number.isInteger(age) || age < 10 || age > 100) {
      throw new ApiError("VALIDATION", "Age must be between 10 and 100.", "age");
    }
  }

  const payload = {
    name,
    age,
    role: patch.role,
    currency: "INR",
    monthly_spending_cap: patch.monthlySpendingCap ? Number(patch.monthlySpendingCap) : null,
    monthly_savings_target: patch.monthlySavingsTarget ? Number(patch.monthlySavingsTarget) : null,
    weekly_study_hours: patch.weeklyStudyHours ? Number(patch.weeklyStudyHours) : null,
    weekly_fitness_minutes: patch.weeklyFitnessMinutes ? Number(patch.weeklyFitnessMinutes) : null,
    weekly_habit_completions: patch.weeklyHabitCompletions ? Number(patch.weeklyHabitCompletions) : null,
    onboarded: true,
  };

  const p = await apiRequest<BackendProfile>("/profile", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  emitChange();
  return mapBackendProfileToFrontend(p);
}

/* ---------------- forecasts & alerts ---------------- */

export interface ForecastPoint {
  date: string;
  predicted: number;
  lower: number;
  upper: number;
}

export interface ForecastResult {
  category: string;
  subcategory: string | null;
  reliability: "insufficient" | "low_confidence" | "reliable";
  data_point_count: number;
  generated_at: string;
  message?: string | null;
  forecast_points: ForecastPoint[];
}

export interface AlertItem {
  id: string;
  category: string;
  subcategory: string | null;
  kind: "threshold" | "trend";
  severity: "info" | "warning" | "risk";
  message: string;
  triggered_at: string;
  resolved_at: string | null;
}

export interface AlertList {
  items: AlertItem[];
  total: number;
}

export async function getForecast(
  category: string,
  subcategory?: string,
  horizonDays = 14,
): Promise<ForecastResult> {
  let url = `/forecast?category=${encodeURIComponent(category)}&horizon_days=${horizonDays}`;
  if (subcategory) {
    url += `&subcategory=${encodeURIComponent(subcategory)}`;
  }
  return apiRequest<ForecastResult>(url);
}

export async function getAlerts(status: "active" | "all" = "active"): Promise<AlertList> {
  return apiRequest<AlertList>(`/alerts?status=${status}`);
}

