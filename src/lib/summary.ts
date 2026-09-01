/** One-line rendering of any entry, regardless of category — used by feeds and tables. */

import { formatCurrency, formatINR } from "./currency";
import type {
  AcademicData,
  Entry,
  FitnessData,
  GoalData,
  HabitData,
  IncomeExpenseData,
  SavingsData,
  StudyData,
} from "./types";

export interface Summary {
  text: string;
  amount: string | null;
  tone: "pos" | "neg" | null;
}

export function entrySummary(e: Entry): Summary {
  switch (e.category) {
    case "income_expense": {
      const d = e.data as IncomeExpenseData;
      return {
        text: d.label || (d.kind === "income" ? "Income" : "Expense"),
        amount: `${d.kind === "expense" ? "−" : "+"}${formatCurrency(d.amount)}`,
        tone: d.kind === "expense" ? "neg" : "pos",
      };
    }
    case "savings": {
      const d = e.data as SavingsData;
      return {
        text: d.vault || "Savings",
        amount: `+${formatCurrency(d.amount)}`,
        tone: "pos",
      };
    }
    case "study": {
      const d = e.data as StudyData;
      return { text: d.topic ? `${d.subject} — ${d.topic}` : d.subject, amount: `${d.hours} h`, tone: null };
    }
    case "academic": {
      const d = e.data as AcademicData;
      const pct = d.maxScore > 0 ? Math.round((d.score / d.maxScore) * 100) : 0;
      return { text: `${d.course} · ${d.assessment}`, amount: `${d.score}/${d.maxScore} (${pct}%)`, tone: pct >= 50 ? "pos" : "neg" };
    }
    case "fitness": {
      const d = e.data as FitnessData;
      return { text: `${d.activity}`, amount: `${d.minutes} min · ${d.intensity}`, tone: null };
    }
    case "habits": {
      const d = e.data as HabitData;
      return { text: d.habit, amount: d.completed ? "done" : "missed", tone: d.completed ? "pos" : "neg" };
    }
    case "goals": {
      const d = e.data as GoalData;
      return {
        text: d.title,
        amount: `${formatINR(d.current)}/${formatINR(d.target)} ${d.unit}`,
        tone: d.target > 0 && d.current / d.target >= 0.5 ? "pos" : null,
      };
    }
  }
}
