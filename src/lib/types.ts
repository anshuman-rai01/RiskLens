/**
 * Domain model — mirrors the Postgres schema sketched in README.md.
 * `entries` is intentionally a single table with a `category` discriminator
 * and a typed payload, so history/permissions stay uniform across sources.
 */

export type Category =
  | "income_expense"
  | "savings"
  | "study"
  | "academic"
  | "fitness"
  | "habits"
  | "goals";

export interface IncomeExpenseData {
  kind: "income" | "expense";
  amount: number;
  label: string;
}

export interface SavingsData {
  amount: number;
  vault: string;
}

export interface StudyData {
  subject: string;
  hours: number;
  topic: string;
}

export interface AcademicData {
  course: string;
  assessment: string;
  score: number;
  maxScore: number;
}

export interface FitnessData {
  activity: string;
  minutes: number;
  intensity: "low" | "moderate" | "high";
}

export interface HabitData {
  habit: string;
  completed: boolean;
}

export interface GoalData {
  title: string;
  unit: string;
  target: number;
  current: number;
  deadline: string | null; // YYYY-MM-DD or open-ended
}

export type EntryData =
  | IncomeExpenseData
  | SavingsData
  | StudyData
  | AcademicData
  | FitnessData
  | HabitData
  | GoalData;

/** A prior version of an entry — edits append here; history is never overwritten. */
export interface Revision {
  data: EntryData;
  occurredOn: string;
  note: string;
  archivedAt: string; // ISO timestamp of the edit
}

export interface Entry {
  id: string;
  userId: string; // isolation boundary — every query filters on this
  category: Category;
  data: EntryData;
  occurredOn: string; // YYYY-MM-DD
  note: string;
  createdAt: string;
  updatedAt: string;
  revisions: Revision[];
  // Extensibility hooks for Milestone 2 (risk-scoring layer). Null for now.
  derived: {
    riskScore?: number;
    thresholdBreached?: boolean;
    impactedGoalIds?: string[];
  } | null;
}

export interface StoredUser {
  id: string;
  email: string; // stored lowercase
  passwordHash: string;
  salt: string;
  iterations: number;
  createdAt: string;
}

export type UserRole = "student" | "professional" | "freelancer" | "other";

/** Self-set compliance baselines live on the profile — the user is their own regulator. */
export interface Profile {
  userId: string;
  name: string;
  age: number | null;
  role: UserRole;
  currency: string;
  monthlySpendingCap: number | null;
  monthlySavingsTarget: number | null;
  weeklyStudyHours: number | null;
  weeklyFitnessMinutes: number | null;
  weeklyHabitCompletions: number | null;
  updatedAt: string;
}

export interface SessionRecord {
  jti: string;
  userId: string;
  createdAt: string;
  expiresAt: string;
  rotatedAt: string;
  userAgent: string;
}

export interface PublicUser {
  id: string;
  email: string;
  createdAt: string;
}

export interface AuthBundle {
  user: PublicUser;
  accessToken: string;
  accessExpiresAt: number; // epoch ms
  refreshToken: string;
}
