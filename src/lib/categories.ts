/**
 * Category registry — one declarative schema per data source.
 * Forms, history tables, and server-side-style validation are all derived from this,
 * so adding an 8th source later is a config change, not a rewrite.
 */

import type { Category } from "./types";

export interface FieldDef {
  key: string;
  label: string;
  type: "text" | "number" | "select" | "toggle" | "date";
  required?: boolean;
  placeholder?: string;
  options?: Array<{ value: string; label: string }>;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  half?: boolean;
  defaultValue?: string | number | boolean;
}

export interface CategoryMeta {
  id: Category;
  label: string;
  short: string;
  tagline: string;
  icon: string;
  accent: string; // hex — used inline, e.g. `${accent}1f` for soft tints
  verb: string;
  fields: FieldDef[];
}

export const CATEGORY_ORDER: Category[] = [
  "income_expense",
  "savings",
  "study",
  "academic",
  "fitness",
  "habits",
  "goals",
];

export const CATEGORIES: Record<Category, CategoryMeta> = {
  income_expense: {
    id: "income_expense",
    label: "Income & Expenses",
    short: "Money",
    tagline: "Every rupee in and out — the base layer of spending-risk.",
    icon: "wallet",
    accent: "#1e5c4f",
    verb: "Log money",
    fields: [
      {
        key: "kind",
        label: "Type",
        type: "select",
        required: true,
        half: true,
        defaultValue: "expense",
        options: [
          { value: "expense", label: "Expense" },
          { value: "income", label: "Income" },
        ],
      },
      { key: "amount", label: "Amount (₹)", type: "number", required: true, half: true, min: 0.01, step: 0.01, placeholder: "850" },
      { key: "label", label: "Description", type: "text", required: true, placeholder: "Groceries, shift payout, metro…" },
    ],
  },
  savings: {
    id: "savings",
    label: "Savings Records",
    short: "Savings",
    tagline: "Transfers into vaults — tracked against your monthly savings target.",
    icon: "vault",
    accent: "#a8811c",
    verb: "Record savings",
    fields: [
      { key: "amount", label: "Amount (₹)", type: "number", required: true, half: true, min: 0.01, step: 0.01, placeholder: "3,000" },
      { key: "vault", label: "Vault / account", type: "text", required: true, half: true, placeholder: "Emergency vault", defaultValue: "" },
    ],
  },
  study: {
    id: "study",
    label: "Study Schedule",
    short: "Study",
    tagline: "Hours per subject — feeds the weekly study-hours baseline.",
    icon: "book",
    accent: "#2c6e8f",
    verb: "Log study time",
    fields: [
      { key: "subject", label: "Subject", type: "text", required: true, half: true, placeholder: "Algorithms" },
      { key: "hours", label: "Hours", type: "number", required: true, half: true, min: 0.25, max: 14, step: 0.25, suffix: "h", placeholder: "1.5" },
      { key: "topic", label: "Topic / activity", type: "text", placeholder: "Problem set 4, past paper…" },
    ],
  },
  academic: {
    id: "academic",
    label: "Academic Performance",
    short: "Grades",
    tagline: "Assessment results — a running record of scores, never overwritten.",
    icon: "gradcap",
    accent: "#56688a",
    verb: "Add result",
    fields: [
      { key: "course", label: "Course", type: "text", required: true, half: true, placeholder: "Statistics" },
      { key: "assessment", label: "Assessment", type: "text", required: true, half: true, placeholder: "Midterm exam" },
      { key: "score", label: "Score", type: "number", required: true, half: true, min: 0, step: 0.5, placeholder: "74" },
      { key: "maxScore", label: "Out of", type: "number", required: true, half: true, min: 1, step: 1, placeholder: "100", defaultValue: 100 },
    ],
  },
  fitness: {
    id: "fitness",
    label: "Fitness Activities",
    short: "Fitness",
    tagline: "Sessions and minutes — feeds the weekly activity baseline.",
    icon: "pulse",
    accent: "#c2473a",
    verb: "Log workout",
    fields: [
      { key: "activity", label: "Activity", type: "text", required: true, placeholder: "5K run, gym, yoga…" },
      { key: "minutes", label: "Minutes", type: "number", required: true, half: true, min: 5, max: 600, step: 5, suffix: "min", placeholder: "45" },
      {
        key: "intensity",
        label: "Intensity",
        type: "select",
        required: true,
        half: true,
        defaultValue: "moderate",
        options: [
          { value: "low", label: "Low" },
          { value: "moderate", label: "Moderate" },
          { value: "high", label: "High" },
        ],
      },
    ],
  },
  habits: {
    id: "habits",
    label: "Habit Tracking",
    short: "Habits",
    tagline: "Daily completions — consistency is the signal.",
    icon: "check",
    accent: "#2e7d53",
    verb: "Log habit",
    fields: [
      { key: "habit", label: "Habit", type: "text", required: true, placeholder: "Read 20 pages" },
      {
        key: "completed",
        label: "Completed today",
        type: "toggle",
        required: true,
        half: true,
        defaultValue: true,
        options: [
          { value: "true", label: "Done" },
          { value: "false", label: "Missed" },
        ],
      },
    ],
  },
  goals: {
    id: "goals",
    label: "Personal Goals",
    short: "Goals",
    tagline: "Target vs. current — every update is kept as revision history.",
    icon: "target",
    accent: "#8c4a63",
    verb: "Set goal",
    fields: [
      { key: "title", label: "Goal", type: "text", required: true, placeholder: "Emergency fund" },
      { key: "unit", label: "Unit", type: "text", required: true, half: true, placeholder: "₹, kg, modules…", defaultValue: "units" },
      { key: "target", label: "Target", type: "number", required: true, half: true, min: 0.01, step: 0.5, placeholder: "1,50,000" },
      { key: "current", label: "Current", type: "number", required: true, half: true, min: 0, step: 0.5, placeholder: "83,000" },
      { key: "deadline", label: "Deadline (optional)", type: "date", half: true },
    ],
  },
};

export const CATEGORY_LIST: CategoryMeta[] = CATEGORY_ORDER.map((c) => CATEGORIES[c]);

export function fieldDefaults(meta: CategoryMeta): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const f of meta.fields) {
    out[f.key] = f.defaultValue ?? (f.type === "toggle" ? false : f.type === "number" ? "" : "");
  }
  return out;
}
