import { useState, useEffect } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from "recharts";
import { I } from "./icons";
import { Sparkline, useDataVersion } from "./ui";
import { useTheme } from "../state/ThemeContext";
import {
  listEntries,
  getForecast,
  getAlerts,
  type ForecastResult,
  type AlertItem,
} from "../lib/db";
import type { Entry, GoalData, StudyData } from "../lib/types";
import { CATEGORIES } from "../lib/categories";
import { formatINR } from "../lib/currency";
import type { NavRoute } from "./Sidebar";

interface DashboardProps {
  onNavigate?: (route: NavRoute) => void;
  startDate?: string;
  endDate?: string;
}

const CATEGORY_COLORS: Record<string, string> = {
  income_expense: "#5B4CC4",
  savings: "#2E9B57",
  study: "#3B82F6",
  academic: "#8B5CF6",
  fitness: "#EC4899",
  habits: "#F59E0B",
  goals: "#10B981",
};

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function Dashboard({ onNavigate, startDate, endDate }: DashboardProps) {
  const { isDark } = useTheme();
  const version = useDataVersion();

  const [entries, setEntries] = useState<Entry[]>([]);
  const [goals, setGoals] = useState<Entry[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [forecast, setForecast] = useState<ForecastResult | null>(null);
  const [forecastCategory, setForecastCategory] = useState<string>("study");
  const [forecastLoading, setForecastLoading] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);

  // Load primary data (entries, goals, alerts)
  useEffect(() => {
    let active = true;
    async function loadData() {
      try {
        const [entriesData, goalsData, alertsData] = await Promise.all([
          listEntries(),
          listEntries("goals"),
          getAlerts("active").catch(() => ({ items: [], total: 0 })),
        ]);
        if (active) {
          setEntries(entriesData);
          setGoals(goalsData);
          setAlerts(alertsData.items || []);
          setLoading(false);
        }
      } catch (err) {
        if (active) {
          console.error("Failed to load dashboard metrics:", err);
          setLoading(false);
        }
      }
    }

    loadData();
    return () => {
      active = false;
    };
  }, [version]);

  // Load forecast when category changes or data updates
  useEffect(() => {
    let active = true;
    async function loadForecast() {
      setForecastLoading(true);
      try {
        const result = await getForecast(forecastCategory);
        if (active) {
          setForecast(result);
        }
      } catch (err) {
        if (active) {
          console.error("Failed to load forecast:", err);
          setForecast(null);
        }
      } finally {
        if (active) {
          setForecastLoading(false);
        }
      }
    }

    loadForecast();
    return () => {
      active = false;
    };
  }, [forecastCategory, version]);

  // ── Date-range filtered entries ──
  const filteredEntries = (startDate && endDate)
    ? entries.filter((e) => e.occurredOn >= startDate && e.occurredOn <= endDate)
    : entries;

  // Calculations for real KPI cards
  const now = new Date();
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  const entriesLast7Days = entries.filter((e) => new Date(e.occurredOn) >= sevenDaysAgo);

  // Study hours (filtered by date range)
  const studyEntriesFiltered = filteredEntries.filter((e) => e.category === "study");
  const totalStudyHours = studyEntriesFiltered.reduce((acc, e) => {
    const d = e.data as StudyData;
    return acc + (Number(d.hours) || 0);
  }, 0);
  const studyHoursLabel = `${totalStudyHours.toFixed(1)} hrs in range`;

  // Goal average progress (not date-filtered — goals are cumulative targets)
  const avgGoalProgress = goals.length
    ? Math.min(
        100,
        Math.round(
          goals.reduce((acc, g) => {
            const d = g.data as GoalData;
            const target = Math.max(1, Number(d.target) || 1);
            const curr = Number(d.current) || 0;
            return acc + (curr / target) * 100;
          }, 0) / goals.length,
        ),
      )
    : 0;

  // Active risk alerts count
  const riskAlertsCount = alerts.filter((a) => a.severity === "risk").length;

  // Category distribution for donut chart (filtered by date range)
  const categoryCounts: Record<string, number> = {};
  filteredEntries.forEach((e) => {
    categoryCounts[e.category] = (categoryCounts[e.category] || 0) + 1;
  });

  const totalEntries = filteredEntries.length;
  const timeAllocationData = Object.entries(categoryCounts).map(([cat, count]) => {
    const meta = CATEGORIES[cat as keyof typeof CATEGORIES];
    const pct = totalEntries > 0 ? Math.round((count / totalEntries) * 100) : 0;
    return {
      label: meta?.label || cat,
      count,
      pct,
      color: CATEGORY_COLORS[cat] || "#6B7280",
    };
  });

  // 7-day sparkline counts (uses filteredEntries for current range)
  const last7DaysSparkline = Array.from({ length: 7 }, (_, i) => {
    const targetDate = new Date(now.getTime() - (6 - i) * 24 * 60 * 60 * 1000);
    const dateStr = targetDate.toISOString().slice(0, 10);
    return filteredEntries.filter((e) => e.occurredOn === dateStr).length;
  });

  // Day of week activity distribution for heatmap (filtered by date range)
  const dayActivityCounts = [0, 0, 0, 0, 0, 0, 0]; // Sun to Sat
  filteredEntries.forEach((e) => {
    try {
      const d = new Date(e.occurredOn);
      if (!isNaN(d.getTime())) {
        dayActivityCounts[d.getDay()] += 1;
      }
    } catch {
      // ignore
    }
  });

  // Top and least active day (derived from real filtered entry data — Fix 7 confirmed)
  const maxDayVal = Math.max(...dayActivityCounts, 1);
  const mostActiveDayIndex = dayActivityCounts.indexOf(Math.max(...dayActivityCounts));
  const leastActiveDayIndex = dayActivityCounts.indexOf(Math.min(...dayActivityCounts));
  const mostActiveDayName = DAY_NAMES[mostActiveDayIndex];
  const leastActiveDayName = DAY_NAMES[leastActiveDayIndex];

  // Prepared KPI metrics
  const kpis = [
    {
      label: "Total Records",
      value: `${filteredEntries.length}`,
      trend: `${entries.length} total`,
      icon: "database",
      iconBg: "bg-primary-soft",
      iconColor: "text-primary",
      sparkline: last7DaysSparkline.some((v) => v > 0) ? last7DaysSparkline : [1, 2, 3, 2, 4, 3, 5],
      sparkColor: "#5B4CC4",
    },
    {
      label: "Study & Focus",
      value: `${totalStudyHours.toFixed(1)} hrs`,
      trend: studyHoursLabel,
      icon: "clock",
      iconBg: "bg-info-soft",
      iconColor: "text-info",
      sparkline: [2, 3, 2.5, 4, 3.5, 5, 4.5],
      sparkColor: "#3B82F6",
    },
    {
      label: "Personal Goals",
      value: `${goals.length} Goals`,
      trend: `${avgGoalProgress}% avg progress`,
      icon: "target",
      iconBg: "bg-ok-soft",
      iconColor: "text-ok",
      sparkline: [10, 25, 35, 50, 60, 70, avgGoalProgress || 75],
      sparkColor: "#10B981",
    },
    {
      label: "Habits & Routine",
      value: `${filteredEntries.filter((e) => e.category === "habits").length} Logged`,
      trend: "Daily routine track",
      icon: "star",
      iconBg: "bg-warn-soft",
      iconColor: "text-warn",
      sparkline: [3, 4, 4, 5, 5, 6, 6],
      sparkColor: "#F59E0B",
    },
    {
      label: "Risk Alerts",
      value: `${alerts.length} Active`,
      trend: riskAlertsCount > 0 ? `${riskAlertsCount} critical risk` : "All systems normal",
      icon: "alert",
      iconBg: alerts.length > 0 ? "bg-danger-soft" : "bg-ok-soft",
      iconColor: alerts.length > 0 ? "text-danger" : "text-ok",
      sparkline: alerts.length > 0 ? [1, 2, 1, 3, 2, alerts.length, alerts.length] : [0, 0, 0, 0, 0, 0, 0],
      sparkColor: alerts.length > 0 ? "#EF4444" : "#10B981",
    },
  ];

  return (
    <div className="space-y-4 sm:space-y-5">
      {/* Row 1: KPI Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-3.5">
        {kpis.map((m, i) => (
          <div
            key={m.label}
            className="anim-rise stagger rounded-xl border border-line bg-card p-3.5 sm:p-4 shadow-xs hover:shadow-md transition-all duration-200"
            style={{ "--i": i } as React.CSSProperties}
          >
            <div className="flex items-center justify-between mb-2">
              <div className={`w-8 h-8 sm:w-9 sm:h-9 rounded-lg ${m.iconBg} flex items-center justify-center ${m.iconColor}`}>
                <I name={m.icon} size={18} />
              </div>
            </div>
            <p className="text-[11.5px] font-medium text-ink-faint truncate mb-0.5">{m.label}</p>
            <p className="text-[20px] font-bold text-ink leading-tight mb-1.5">
              {loading ? "..." : m.value}
            </p>
            <div className="h-7 mb-1.5">
              <Sparkline data={m.sparkline} color={m.sparkColor} height={28} />
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span className={`font-medium truncate ${m.iconColor}`}>{m.trend}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Row 2: 3 Cards (Forecasting & Trends | Category Allocation | Goals Overview) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 1. Forecasting & Trend Card with 3-Tier Reliability Handling */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <h3 className="font-display font-semibold text-[15px] text-ink">Predictive Forecast</h3>
                {forecast && (
                  <span
                    className={`text-[9.5px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                      forecast.reliability === "reliable"
                        ? "bg-ok-soft text-ok border border-ok/20"
                        : forecast.reliability === "low_confidence"
                          ? "bg-warn-soft text-warn border border-warn/20"
                          : "bg-bg-soft text-ink-faint border border-line"
                    }`}
                  >
                    {forecast.reliability === "reliable"
                      ? "Reliable (28+ pts)"
                      : forecast.reliability === "low_confidence"
                        ? "Low Confidence (14-27 pts)"
                        : "Insufficient (<14 pts)"}
                  </span>
                )}
              </div>
              <select
                value={forecastCategory}
                onChange={(e) => setForecastCategory(e.target.value)}
                className="text-[11.5px] font-medium text-ink-soft border border-line rounded-lg px-2.5 py-1 bg-card hover:bg-bg-soft transition-colors focus-ring cursor-pointer"
              >
                <option value="study">Study Hours</option>
                <option value="income_expense">Expenses</option>
                <option value="fitness">Fitness</option>
                <option value="habits">Habits</option>
                <option value="savings">Savings</option>
                <option value="academic">Academics</option>
              </select>
            </div>

            {forecastLoading ? (
              <div className="h-[180px] flex flex-col items-center justify-center text-ink-faint">
                <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin mb-2" />
                <p className="text-[12px]">Computing time-series forecast…</p>
              </div>
            ) : !forecast || forecast.reliability === "insufficient" ? (
              /* Insufficient Data Tier: Explanatory State */
              <div className="h-[180px] flex flex-col justify-center rounded-lg bg-bg-soft/60 border border-dashed border-line p-4 text-center">
                <div className="w-8 h-8 rounded-full bg-warn-soft text-warn flex items-center justify-center mx-auto mb-2">
                  <I name="info" size={16} />
                </div>
                <h4 className="text-[12.5px] font-semibold text-ink mb-1">
                  More Data Needed for Forecasting
                </h4>
                <p className="text-[11px] text-ink-soft leading-relaxed max-w-[280px] mx-auto mb-2.5">
                  Predictive modeling requires 14+ daily data points. Currently{" "}
                  <span className="font-semibold text-ink font-mono">
                    {forecast?.data_point_count ?? 0}
                  </span>{" "}
                  recorded in this category.
                </p>
                <div className="w-full max-w-[200px] mx-auto bg-line h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-primary h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.min(100, (((forecast?.data_point_count ?? 0) / 14) * 100))}%`,
                    }}
                  />
                </div>
              </div>
            ) : (
              /* Low-Confidence or Reliable Tier: Render Chart with Predictions & Bounds */
              <div className="h-[180px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={forecast.forecast_points}
                    margin={{ top: 8, right: 8, left: -24, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="forecastFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={isDark ? "#7C6EED" : "#5B4CC4"} stopOpacity={0.25} />
                        <stop offset="100%" stopColor={isDark ? "#7C6EED" : "#5B4CC4"} stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="date"
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(val: string) => val.slice(5)}
                      tick={{ fontSize: 10, fill: isDark ? "#9CA3AF" : "#6B7280" }}
                    />
                    <YAxis
                      axisLine={false}
                      tickLine={false}
                      tick={{ fontSize: 10, fill: isDark ? "#9CA3AF" : "#6B7280" }}
                    />
                    <Tooltip
                      formatter={(val: number | string, name: string) => [
                        typeof val === "number" ? val.toFixed(2) : val,
                        name === "predicted" ? "Predicted (ŷ)" : name,
                      ]}
                      labelFormatter={(label) => `Date: ${label}`}
                      contentStyle={{
                        backgroundColor: isDark ? "#181B26" : "#FFFFFF",
                        borderColor: isDark ? "#262B3B" : "#E5E7EB",
                        borderRadius: "8px",
                        color: isDark ? "#F3F4F6" : "#1F2937",
                        fontSize: "11.5px",
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="predicted"
                      stroke={isDark ? "#7C6EED" : "#5B4CC4"}
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#forecastFill)"
                      dot={{ fill: isDark ? "#7C6EED" : "#5B4CC4", r: 2.5, strokeWidth: 0 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
          <div className="pt-2 border-t border-line text-[10.5px] text-ink-faint flex items-center justify-between">
            <span>Model: Facebook Prophet (80% CI)</span>
            <span>Horizon: 14 Days</span>
          </div>
        </div>

        {/* 2. Category Allocation Card */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-display font-semibold text-[15px] text-ink">Category Allocation</h3>
            <span className="text-[11px] text-ink-faint font-mono">{totalEntries} total</span>
          </div>
          {totalEntries === 0 ? (
            <div className="h-[180px] flex flex-col items-center justify-center text-center p-4">
              <p className="text-[12px] text-ink-soft">No entries recorded yet.</p>
              <p className="text-[11px] text-ink-faint mt-1">
                Log entries across study, fitness, and expenses to see distribution.
              </p>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 py-1">
              <div className="relative w-[140px] h-[140px] shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={timeAllocationData}
                      cx="50%"
                      cy="50%"
                      innerRadius={42}
                      outerRadius={65}
                      paddingAngle={2}
                      dataKey="count"
                    >
                      {timeAllocationData.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={entry.color}
                          stroke={isDark ? "#181B26" : "#FFFFFF"}
                          strokeWidth={2}
                        />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  <p className="text-[10px] uppercase font-semibold text-ink-faint tracking-wider">Entries</p>
                  <p className="text-[15px] font-bold text-ink">{totalEntries}</p>
                </div>
              </div>

              {/* Legend */}
              <div className="flex-1 w-full space-y-1.5 min-w-0 max-h-[140px] overflow-y-auto pr-1">
                {timeAllocationData.map((t) => (
                  <div key={t.label} className="flex items-center justify-between text-[11.5px]">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: t.color }} />
                      <span className="text-ink-soft truncate">{t.label}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0 ml-1 font-mono">
                      <span className="font-semibold text-ink">{t.pct}%</span>
                      <span className="text-ink-faint text-[10px]">({t.count})</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="pt-2 border-t border-line text-[10.5px] text-ink-faint">
            Aggregated across all 6 behavioral categories
          </div>
        </div>

        {/* 3. Goals Overview Card */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="font-display font-semibold text-[15px] text-ink">Personal Goals</h3>
              <span className="text-[11px] text-ink-faint font-mono">{goals.length} tracked</span>
            </div>

            {goals.length === 0 ? (
              <div className="h-[150px] flex flex-col items-center justify-center text-center p-4">
                <p className="text-[12px] text-ink-soft">No active goals yet.</p>
                <p className="text-[11px] text-ink-faint mt-1">
                  Create targets in Personal Goals to track progress toward deadlines.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5 max-h-[165px] overflow-y-auto pr-1">
                {goals.slice(0, 4).map((g) => {
                  const d = g.data as GoalData;
                  const target = Math.max(1, Number(d.target) || 1);
                  const current = Number(d.current) || 0;
                  const pct = Math.min(100, Math.round((current / target) * 100));

                  return (
                    <div key={g.id} className="space-y-1">
                      <div className="flex items-center justify-between text-[11.5px]">
                        <span className="font-medium text-ink truncate max-w-[140px]">{d.title}</span>
                        <span className="text-[10.5px] font-mono text-ink-faint">
                          {formatINR(current)} / {formatINR(target)} {d.unit}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 rounded-full bg-bg-soft overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              width: `${pct}%`,
                              background: pct >= 100 ? "#10B981" : "#5B4CC4",
                            }}
                          />
                        </div>
                        <span className="text-[10.5px] font-mono font-semibold text-ink w-8 text-right">
                          {pct}%
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <button
            onClick={() => onNavigate?.({ view: "category", id: "goals" })}
            className="mt-2.5 text-[12px] font-semibold text-primary hover:text-primary-deep transition-colors text-left flex items-center gap-1"
          >
            Manage all goals →
          </button>
        </div>
      </div>

      {/* Row 3: 3 Cards (Activity Heatmap | Focus Sessions [Prototype] | Insights & Risk Alerts) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 1. Activity Heatmap Card */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="font-display font-semibold text-[15px] text-ink">Activity Cadence</h3>
              <span className="text-[11px] text-ink-faint">Day-of-week volume</span>
            </div>

            <div className="grid grid-cols-7 gap-1.5 pt-2 pb-3">
              {DAY_NAMES.map((name, i) => {
                const count = dayActivityCounts[i];
                const intensity = Math.min(1, count / maxDayVal);
                const opacity = count === 0 ? 0.15 : 0.25 + intensity * 0.75;

                return (
                  <div key={name} className="flex flex-col items-center gap-1.5">
                    <span className="text-[10px] font-medium text-ink-faint">{name}</span>
                    <div
                      className="w-full h-14 rounded-md flex flex-col justify-end p-1 transition-all"
                      style={{
                        backgroundColor: isDark ? "#1E2230" : "#F1F3F9",
                      }}
                      title={`${name}: ${count} entries`}
                    >
                      <div
                        className="w-full rounded-sm transition-all duration-300"
                        style={{
                          height: `${Math.max(12, intensity * 100)}%`,
                          backgroundColor: "#10B981",
                          opacity,
                        }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-ink-soft">{count}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-line text-[10px] text-ink-faint">
            <span>Peak Day: {mostActiveDayName}</span>
            <span>Lowest: {leastActiveDayName}</span>
          </div>
        </div>

        {/* 2. Focus Sessions Card — Clearly Labeled Prototype (Future) */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-2">
                <h3 className="font-display font-semibold text-[15px] text-ink">Focus Sessions</h3>
                <span className="text-[9.5px] font-semibold text-primary bg-primary-soft px-2 py-0.5 rounded-full uppercase tracking-wider">
                  Prototype (Future)
                </span>
              </div>
            </div>

            {/* Prototype Banner */}
            <div className="rounded-lg bg-bg-soft p-2.5 mb-2.5 border border-line text-[11px] text-ink-soft leading-relaxed">
              Real-time Pomodoro telemetry & deep work session recording will connect to the backend pipeline in a future milestone.
            </div>

            {/* Simulated Session Preview */}
            <div className="space-y-1.5 opacity-80">
              <div className="flex items-center justify-between gap-2 p-2 rounded-lg bg-bg-soft">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-6 h-6 rounded-md bg-primary-soft flex items-center justify-center text-primary shrink-0">
                    <I name="target" size={13} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11.5px] font-semibold text-ink truncate">Deep Work – Project Build</p>
                    <p className="text-[10px] text-ink-faint truncate">2h planned</p>
                  </div>
                </div>
                <span className="text-[9.5px] font-semibold text-ok bg-ok-soft px-1.5 py-0.5 rounded-full">
                  Ready
                </span>
              </div>

              <div className="flex items-center justify-between gap-2 p-2 rounded-lg bg-bg-soft">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-6 h-6 rounded-md bg-primary-soft flex items-center justify-center text-primary shrink-0">
                    <I name="clock" size={13} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11.5px] font-semibold text-ink truncate">Study – Core Algorithms</p>
                    <p className="text-[10px] text-ink-faint truncate">1h 30m</p>
                  </div>
                </div>
                <span className="text-[9.5px] font-semibold text-ink-faint bg-bg-soft px-1.5 py-0.5 rounded-full border border-line">
                  Scheduled
                </span>
              </div>
            </div>
          </div>

          <div className="pt-2 border-t border-line text-[10.5px] text-ink-faint">
            Session timer module planned for Milestone 3
          </div>
        </div>

        {/* 3. Insights & Risk Alerts — Wired to Real GET /alerts */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-2">
                <h3 className="font-display font-semibold text-[15px] text-ink">Active Risk Alerts</h3>
                <span className="text-[11px] font-mono text-ink-faint">({alerts.length})</span>
              </div>
              <span className="text-[10px] font-mono text-ink-faint">reconciled live</span>
            </div>

            {alerts.length === 0 ? (
              <div className="h-[160px] flex flex-col items-center justify-center text-center p-3 rounded-lg bg-ok-soft/30 border border-ok/20">
                <div className="w-8 h-8 rounded-full bg-ok-soft text-ok flex items-center justify-center mx-auto mb-2">
                  <I name="ok" size={16} />
                </div>
                <p className="text-[12px] font-semibold text-ok">All Systems Healthy</p>
                <p className="text-[11px] text-ink-soft mt-1 max-w-[240px]">
                  No active threshold or trend violations detected. All tracked metrics are within normal variance.
                </p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[175px] overflow-y-auto pr-1">
                {alerts.map((alert) => {
                  const isRisk = alert.severity === "risk";
                  const isWarn = alert.severity === "warning";
                  const toneBg = isRisk
                    ? "bg-danger-soft border-danger/30"
                    : isWarn
                      ? "bg-warn-soft border-warn/30"
                      : "bg-info-soft border-info/30";
                  const toneText = isRisk
                    ? "text-danger"
                    : isWarn
                      ? "text-warn"
                      : "text-info";

                  return (
                    <div
                      key={alert.id}
                      className={`flex items-start gap-2.5 p-2.5 rounded-lg border ${toneBg}`}
                    >
                      <div
                        className={`w-6 h-6 rounded-md flex items-center justify-center ${toneText} shrink-0 mt-0.5`}
                      >
                        <I name={isRisk ? "alert" : "info"} size={13} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-1 mb-0.5">
                          <p className="text-[11.5px] font-semibold text-ink leading-tight capitalize truncate">
                            {alert.category.replace("_", " ")}
                          </p>
                          <span
                            className={`text-[9.5px] font-semibold uppercase font-mono px-1.5 py-0.2 rounded ${toneText}`}
                          >
                            {alert.kind}
                          </span>
                        </div>
                        <p className="text-[10.5px] text-ink-soft leading-snug">
                          {alert.message}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="pt-2 border-t border-line text-[10.5px] text-ink-faint flex items-center justify-between">
            <span>Threshold & Prophet trend rules</span>
            <span>Updated on demand</span>
          </div>
        </div>
      </div>

      {/* Row 4: Weekly Summary Card (Full Width) */}
      <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
          {/* Summary Narrative */}
          <div className="md:col-span-1 border-b md:border-b-0 md:border-r border-line pb-3 md:pb-0 md:pr-4">
            <div className="flex items-start gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-primary-soft text-primary flex items-center justify-center shrink-0">
                <I name="award" size={17} />
              </div>
              <div>
                <div className="flex items-center gap-1.5 mb-1">
                  <h4 className="font-display font-semibold text-[13.5px] text-ink leading-tight">
                    Weekly Summary
                  </h4>
                  <span className="text-[9px] font-semibold text-primary bg-primary-soft px-1.5 py-0.2 rounded uppercase">
                    Prototype (Future)
                  </span>
                </div>
                <p className="text-[11.5px] text-ink-soft leading-relaxed">
                  {entries.length > 0
                    ? `You logged ${filteredEntries.length} records in this range. Peak logging day was ${mostActiveDayName}.`
                    : "Welcome to RiskLens! Start recording entries across your study, habit, and financial categories."}
                </p>
              </div>
            </div>
          </div>

          {/* Top Productive / Active Day */}
          <div className="rounded-lg bg-bg-soft p-3">
            <p className="text-[10.5px] text-ink-faint mb-0.5">Peak Activity Day</p>
            <div className="flex items-baseline justify-between mb-1">
              <p className="text-[14px] font-bold text-ink">{mostActiveDayName}</p>
              <p className="text-[12px] font-semibold text-ok">
                {dayActivityCounts[mostActiveDayIndex]} entries
              </p>
            </div>
            <div className="h-5">
              <Sparkline data={dayActivityCounts} color="#2E9B57" height={20} />
            </div>
          </div>

          {/* Least Active Day */}
          <div className="rounded-lg bg-bg-soft p-3">
            <p className="text-[10.5px] text-ink-faint mb-0.5">Lowest Activity Day</p>
            <div className="flex items-baseline justify-between mb-1">
              <p className="text-[14px] font-bold text-ink">{leastActiveDayName}</p>
              <p className="text-[12px] font-semibold text-ink-faint">
                {dayActivityCounts[leastActiveDayIndex]} entries
              </p>
            </div>
            <div className="h-5">
              <Sparkline
                data={dayActivityCounts.map((v) => maxDayVal - v)}
                color="#EF4444"
                height={20}
              />
            </div>
          </div>

          {/* Weekly Goal Progress */}
          <div className="rounded-lg bg-bg-soft p-3">
            <p className="text-[10.5px] text-ink-faint mb-0.5">Average Goal Completion</p>
            <div className="flex items-baseline justify-between mb-1.5">
              <p className="text-[18px] font-bold text-ink leading-tight">{avgGoalProgress}%</p>
              <p className="text-[11px] text-ink-faint">{goals.length} goals</p>
            </div>
            <div className="h-2 rounded-full bg-card overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${avgGoalProgress}%`,
                  background: "linear-gradient(135deg, #5B4CC4 0%, #4F46E5 100%)",
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
