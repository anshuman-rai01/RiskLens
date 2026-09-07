/**
 * Category registry — productivity-focused labels.
 * The underlying data model stays the same; only display labels change.
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
  accent: string;
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
    label: "Insights & Reports",
    short: "Insights",
    tagline: "Track your financial patterns and spending insights.",
    icon: "chart",
    accent: "#5B4CC4",
    verb: "Log insight",
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
      { key: "label", label: "Description", type: "text", required: true, placeholder: "Coffee, groceries, freelance work…" },
    ],
  },
  savings: {
    id: "savings",
    label: "Calendar View",
    short: "Calendar",
    tagline: "Plan and track your savings goals over time.",
    icon: "calendar",
    accent: "#F59E0B",
    verb: "Record savings",
    fields: [
      { key: "amount", label: "Amount (₹)", type: "number", required: true, half: true, min: 0.01, step: 0.01, placeholder: "3,000" },
      { key: "vault", label: "Goal / account", type: "text", required: true, half: true, placeholder: "Emergency fund", defaultValue: "" },
    ],
  },
  study: {
    id: "study",
    label: "Productivity Analysis",
    short: "Productivity",
    tagline: "Analyze your learning patterns and study sessions.",
    icon: "brain",
    accent: "#3B82F6",
    verb: "Log session",
    fields: [
      { key: "subject", label: "Subject", type: "text", required: true, half: true, placeholder: "Machine Learning" },
      { key: "hours", label: "Hours", type: "number", required: true, half: true, min: 0.25, max: 14, step: 0.25, suffix: "h", placeholder: "1.5" },
      { key: "topic", label: "Topic / activity", type: "text", placeholder: "Deep work, revision, practice…" },
    ],
  },
  academic: {
    id: "academic",
    label: "Focus Sessions",
    short: "Focus",
    tagline: "Track your focused work sessions and achievements.",
    icon: "target",
    accent: "#2E9B57",
    verb: "Log session",
    fields: [
      { key: "course", label: "Project", type: "text", required: true, half: true, placeholder: "ML Algorithms" },
      { key: "assessment", label: "Session type", type: "text", required: true, half: true, placeholder: "Deep work" },
      { key: "score", label: "Duration (min)", type: "number", required: true, half: true, min: 0, step: 5, placeholder: "90" },
      { key: "maxScore", label: "Target (min)", type: "number", required: true, half: true, min: 1, step: 5, placeholder: "120", defaultValue: 120 },
    ],
  },
  fitness: {
    id: "fitness",
    label: "Activity Tracker",
    short: "Activity",
    tagline: "Monitor your physical activities and movement.",
    icon: "activity",
    accent: "#EF4444",
    verb: "Log activity",
    fields: [
      { key: "activity", label: "Activity", type: "text", required: true, placeholder: "Running, yoga, gym…" },
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
    label: "Habit Tracker",
    short: "Habits",
    tagline: "Build consistency with daily habit tracking.",
    icon: "check",
    accent: "#2E9B57",
    verb: "Log habit",
    fields: [
      { key: "habit", label: "Habit", type: "text", required: true, placeholder: "Meditate 10 minutes" },
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
    label: "Goals",
    short: "Goals",
    tagline: "Set targets and track your progress over time.",
    icon: "flag",
    accent: "#8B5CF6",
    verb: "Set goal",
    fields: [
      { key: "title", label: "Goal", type: "text", required: true, placeholder: "Read 50 books this year" },
      { key: "unit", label: "Unit", type: "text", required: true, half: true, placeholder: "₹, books, hours…", defaultValue: "units" },
      { key: "target", label: "Target", type: "number", required: true, half: true, min: 0.01, step: 0.5, placeholder: "50" },
      { key: "current", label: "Current", type: "number", required: true, half: true, min: 0, step: 0.5, placeholder: "23" },
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
