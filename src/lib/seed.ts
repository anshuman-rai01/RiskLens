/**
 * Deterministic demo dataset — lets reviewers see a populated system on first run.
 * Exercises every category, revision history, and both compliance states.
 */

import { hashPassword } from "./crypto";
import { uid } from "./store";
import type { Entry, EntryData, Profile, Revision, StoredUser, Category } from "./types";

export const DEMO_EMAIL = "demo@risklens.app";
export const DEMO_PASSWORD = "Demo1234!";

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function dayISO(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() - offsetDays);
  return d.toISOString().slice(0, 10);
}

function ts(offsetDays: number, hour: number, min: number): string {
  const d = new Date();
  d.setDate(d.getDate() - offsetDays);
  d.setHours(hour, min, 0, 0);
  return d.toISOString();
}

const SUBJECTS = ["Algorithms", "Statistics", "Database Systems", "Microeconomics"];
const TOPICS = ["lecture notes", "problem set", "past paper", "group review", "flashcards", "lab work"];
const EXPENSES: Array<[string, number, number]> = [
  ["Groceries", 9, 34],
  ["Campus lunch", 5, 12],
  ["Transit top-up", 6, 15],
  ["Coffee", 3, 7],
  ["Data bundle", 8, 18],
  ["Cinema night", 10, 16],
  ["Textbook chapter", 9, 22],
  ["Gym smoothie", 5, 9],
  ["Laundry", 6, 10],
  ["Cloud storage", 3, 6],
];
const FITNESS: Array<[string, "low" | "moderate" | "high"]> = [
  ["5K run", "moderate"],
  ["Gym — upper body", "high"],
  ["Yoga flow", "low"],
  ["Cycling loop", "moderate"],
  ["Gym — legs", "high"],
  ["Swim intervals", "moderate"],
];

export async function buildDemoRows(): Promise<{ user: StoredUser; profile: Profile; entries: Entry[] }> {
  const userId = uid("usr");
  const { salt, hash, iterations } = await hashPassword(DEMO_PASSWORD);
  const createdAt = ts(62, 9, 12);

  const user: StoredUser = {
    id: userId,
    email: DEMO_EMAIL,
    passwordHash: hash,
    salt,
    iterations,
    createdAt,
  };

  const profile: Profile = {
    userId,
    name: "Amara Osei",
    age: 22,
    role: "student",
    currency: "$",
    monthlySpendingCap: 900,
    monthlySavingsTarget: 250,
    weeklyStudyHours: 14,
    weeklyFitnessMinutes: 150,
    weeklyHabitCompletions: 12,
    updatedAt: ts(40, 18, 0),
  };

  const entries = buildSampleEntries(userId);
  return { user, profile, entries };
}

/** Sample history for any user id — powers "generate sample data" for fresh accounts. */
export function buildSampleEntries(userId: string): Entry[] {
  const rnd = mulberry32(424242);
  const entries: Entry[] = [];

  const push = (category: Category, data: EntryData, offset: number, hour: number, note = "", revisions: Revision[] = []) => {
    entries.push({
      id: uid("ent"),
      userId,
      category,
      data,
      occurredOn: dayISO(offset),
      note,
      createdAt: ts(offset, hour, Math.floor(rnd() * 50) + 5),
      updatedAt: ts(offset, hour + 1, 10),
      revisions,
      derived: null,
    });
  };

  for (let i = 56; i >= 0; i--) {
    // ---- income & expenses ----
    const roll = rnd();
    const count = roll < 0.1 ? 0 : roll < 0.72 ? 1 : 2;
    for (let k = 0; k < count; k++) {
      const [label, lo, hi] = EXPENSES[Math.floor(rnd() * EXPENSES.length)];
      const amount = Math.round((lo + rnd() * (hi - lo)) * 100) / 100;
      push("income_expense", { kind: "expense", amount, label }, i, 12 + k * 3, "");
    }
    if (i % 14 === 3) push("income_expense", { kind: "income", amount: 2400, label: "Part-time shift payout" }, i, 9);
    if (rnd() < 0.06)
      push("income_expense", { kind: "income", amount: Math.round(90 + rnd() * 70), label: "Tutoring session" }, i, 17);

    // ---- savings ----
    if (i % 7 === 1)
      push("savings", { amount: Math.round(45 + rnd() * 35), vault: "Emergency vault" }, i, 8, "Auto-transfer");

    // ---- study ----
    if (rnd() < 0.82) {
      const sessions = rnd() < 0.35 ? 2 : 1;
      for (let k = 0; k < sessions; k++) {
        const hours = Math.round((0.75 + rnd() * 2.5) * 4) / 4;
        push(
          "study",
          { subject: SUBJECTS[Math.floor(rnd() * SUBJECTS.length)], hours, topic: TOPICS[Math.floor(rnd() * TOPICS.length)] },
          i,
          15 + k * 3,
        );
      }
    }

    // ---- fitness ----
    if (rnd() < 0.55) {
      const [activity, intensity] = FITNESS[Math.floor(rnd() * FITNESS.length)];
      const minutes = Math.round(25 + rnd() * 50);
      push("fitness", { activity, minutes, intensity }, i, 7);
    }

    // ---- habits ----
    push("habits", { habit: "Read 20 pages", completed: rnd() < 0.8 }, i, 21);
    push("habits", { habit: "Lights out by 23:30", completed: rnd() < 0.68 }, i, 23);
  }

  // ---- academic ----
  const assessments: Array<[string, string, number, number, number]> = [
    ["Algorithms", "Midterm exam", 74, 100, 48],
    ["Statistics", "Quiz 3", 17, 20, 41],
    ["Database Systems", "Project milestone 1", 88, 100, 35],
    ["Microeconomics", "Problem set 4", 9, 10, 28],
    ["Algorithms", "Lab practical", 16, 20, 21],
    ["Statistics", "Midterm exam", 61, 100, 14],
    ["Database Systems", "Quiz 1", 18, 20, 9],
    ["Microeconomics", "Essay draft", 72, 100, 4],
  ];
  for (const [course, assessment, score, maxScore, offset] of assessments) {
    push("academic", { course, assessment, score, maxScore }, offset, 11, "");
  }

  // ---- goals (with revision history — progress is preserved, never overwritten) ----
  entries.push({
    id: uid("ent"),
    userId,
    category: "goals",
    data: { title: "Emergency fund", unit: "$", target: 1500, current: 830, deadline: dayISO(-88) },
    occurredOn: dayISO(50),
    note: "3-month runway target",
    createdAt: ts(50, 10, 0),
    updatedAt: ts(2, 19, 30),
    revisions: [
      {
        data: { title: "Emergency fund", unit: "$", target: 1500, current: 410, deadline: dayISO(-88) },
        occurredOn: dayISO(50),
        note: "",
        archivedAt: ts(30, 20, 0),
      },
      {
        data: { title: "Emergency fund", unit: "$", target: 1500, current: 640, deadline: dayISO(-88) },
        occurredOn: dayISO(50),
        note: "",
        archivedAt: ts(14, 20, 15),
      },
    ],
    derived: null,
  });
  entries.push({
    id: uid("ent"),
    userId,
    category: "goals",
    data: { title: "Finish DSA course", unit: "modules", target: 42, current: 27, deadline: dayISO(-26) },
    occurredOn: dayISO(34),
    note: "",
    createdAt: ts(34, 14, 0),
    updatedAt: ts(1, 21, 0),
    revisions: [
      {
        data: { title: "Finish DSA course", unit: "modules", target: 42, current: 12, deadline: dayISO(-26) },
        occurredOn: dayISO(34),
        note: "",
        archivedAt: ts(16, 21, 0),
      },
    ],
    derived: null,
  });
  entries.push({
    id: uid("ent"),
    userId,
    category: "goals",
    data: { title: "Bench press", unit: "kg", target: 80, current: 62.5, deadline: dayISO(-60) },
    occurredOn: dayISO(40),
    note: "1RM target",
    createdAt: ts(40, 8, 0),
    updatedAt: ts(3, 8, 45),
    revisions: [],
    derived: null,
  });

  return entries;
}
