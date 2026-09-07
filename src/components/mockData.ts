/**
 * Mock data for the Productivity & Habit Analysis Engine dashboard.
 * In a real deployment this would come from the repository layer.
 */

export interface KpiMetric {
  label: string;
  value: string;
  trend: string;
  trendPct: number;
  icon: string;
  iconBg: string;
  iconColor: string;
  sparkline: number[];
  sparkColor: string;
  secondary?: string;
  emoji?: string;
}

export interface HabitRow {
  name: string;
  completed: number;
  total: number;
  streak: number;
  color: string;
}

export interface FocusSession {
  title: string;
  time: string;
  duration: string;
  status: "completed" | "in-progress" | "missed";
}

export interface Insight {
  icon: string;
  title: string;
  body: string;
  tone: "ok" | "warn" | "primary" | "info";
}

export const kpiMetrics: KpiMetric[] = [
  {
    label: "Productivity Score",
    value: "7.8 / 10.0",
    trend: "↑ 12% vs last week",
    trendPct: 12,
    icon: "zap",
    iconBg: "bg-primary-soft",
    iconColor: "text-primary",
    sparkline: [5.2, 6.1, 5.8, 7.2, 6.9, 7.5, 7.8],
    sparkColor: "#5B4CC4",
  },
  {
    label: "Focus Time",
    value: "18h 45m",
    trend: "↑ 15% vs last week",
    trendPct: 15,
    icon: "clock",
    iconBg: "bg-info-soft",
    iconColor: "text-info",
    sparkline: [12, 14, 13, 16, 15, 17, 18.75],
    sparkColor: "#3B82F6",
  },
  {
    label: "Tasks Completed",
    value: "42 / 58",
    trend: "↑ 20% vs last week",
    trendPct: 20,
    icon: "clipboard",
    iconBg: "bg-ok-soft",
    iconColor: "text-ok",
    sparkline: [28, 32, 30, 38, 35, 40, 42],
    sparkColor: "#2E9B57",
  },
  {
    label: "Habit Score",
    value: "82 / 100",
    trend: "↑ 10% vs last week",
    trendPct: 10,
    icon: "star",
    iconBg: "bg-warn-soft",
    iconColor: "text-warn",
    sparkline: [60, 65, 68, 72, 75, 78, 82],
    sparkColor: "#F59E0B",
  },
  {
    label: "Current Streak",
    value: "12 Days",
    trend: "Best: 18 Days",
    trendPct: 0,
    icon: "flame",
    iconBg: "bg-danger-soft",
    iconColor: "text-danger",
    sparkline: [4, 6, 8, 9, 10, 11, 12],
    sparkColor: "#EF4444",
    secondary: "Longest: 18 Days",
    emoji: "🔥",
  },
];

export const productivityTrend = [
  { day: "Mon", value: 72 },
  { day: "Tue", value: 68 },
  { day: "Wed", value: 88 },
  { day: "Thu", value: 82 },
  { day: "Fri", value: 76 },
  { day: "Sat", value: 64 },
  { day: "Sun", value: 58 },
];

export const timeAllocation = [
  { label: "Deep Work", pct: 40, time: "9h 50m", color: "#5B4CC4" },
  { label: "Learning", pct: 20, time: "4h 55m", color: "#3B82F6" },
  { label: "Meetings", pct: 15, time: "3h 40m", color: "#F59E0B" },
  { label: "Admin Work", pct: 10, time: "2h 25m", color: "#6B7280" },
  { label: "Breaks", pct: 15, time: "3h 40m", color: "#2E9B57" },
];

export const habits: HabitRow[] = [
  { name: "Wake up early", completed: 6, total: 7, streak: 12, color: "#5B4CC4" },
  { name: "Exercise", completed: 5, total: 7, streak: 8, color: "#EF4444" },
  { name: "Meditation", completed: 6, total: 7, streak: 14, color: "#2E9B57" },
  { name: "Read books", completed: 5, total: 7, streak: 7, color: "#3B82F6" },
  { name: "No sugar", completed: 4, total: 7, streak: 5, color: "#F59E0B" },
];

export const focusSessions: FocusSession[] = [
  { title: "Deep Work – Project A", time: "9:00 AM – 11:00 AM", duration: "120 min", status: "completed" },
  { title: "Study – ML Algorithms", time: "12:30 PM – 2:00 PM", duration: "90 min", status: "completed" },
  { title: "Report Writing", time: "3:30 PM – 5:00 PM", duration: "90 min", status: "completed" },
];

export const insights: Insight[] = [
  {
    icon: "trendUp",
    title: "Peak productivity on Wed & Thu",
    body: "Your productivity is higher on Wednesday and Thursday. Try to schedule deep work on these days.",
    tone: "primary",
  },
  {
    icon: "clock",
    title: "Deep work dominance",
    body: "You spend most of your time in deep work. Great job! Keep it up.",
    tone: "ok",
  },
  {
    icon: "star",
    title: "Exercise habit needs attention",
    body: "Your exercise habit can improve. Try to maintain consistency.",
    tone: "warn",
  },
  {
    icon: "award",
    title: "Excellent focus session rate",
    body: "You have an 87% focus session success rate. Excellent work!",
    tone: "info",
  },
];

export const weeklySummary = {
  message: "You were most productive on Wednesday with a score of 88. Keep maintaining your consistency!",
  topDay: { day: "Wednesday", score: 88, sparkline: [60, 70, 80, 88, 82, 75, 70] },
  leastDay: { day: "Sunday", score: 58, sparkline: [70, 65, 60, 58, 55, 52, 58] },
  goalProgress: { current: 85, target: 90 },
};

export const activityHeatmap: number[][] = [
  // 6 AM, 9 AM, 12 PM, 3 PM, 6 PM, 9 PM — for Mon-Sun
  [1, 3, 4, 2, 1, 0], // Mon
  [2, 4, 3, 3, 2, 1], // Tue
  [3, 5, 4, 4, 3, 2], // Wed
  [2, 4, 5, 4, 3, 1], // Thu
  [1, 3, 3, 2, 2, 1], // Fri
  [0, 2, 2, 1, 1, 0], // Sat
  [0, 1, 1, 1, 0, 0], // Sun
];

export const dailyQuotes = [
  "Small daily improvements lead to stunning results.",
  "The secret of getting ahead is getting started.",
  "Focus on being productive instead of busy.",
  "Discipline is the bridge between goals and accomplishment.",
  "Your future is created by what you do today.",
];
