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
import { Sparkline } from "./ui";
import { useTheme } from "../state/ThemeContext";
import {
  kpiMetrics,
  productivityTrend,
  timeAllocation,
  habits,
  focusSessions,
  insights,
  weeklySummary,
  activityHeatmap,
} from "./mockData";

const HEATMAP_LABELS = ["6 AM", "9 AM", "12 PM", "3 PM", "6 PM", "9 PM"];
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function getHeatColor(value: number, isDark: boolean): string {
  if (isDark) {
    if (value === 0) return "#1E2230";
    if (value === 1) return "#064e3b";
    if (value === 2) return "#047857";
    if (value === 3) return "#059669";
    if (value === 4) return "#10B981";
    return "#34D399";
  }
  if (value === 0) return "#F1F3F9";
  if (value === 1) return "#D1FAE5";
  if (value === 2) return "#6EE7B7";
  if (value === 3) return "#34D399";
  if (value === 4) return "#10B981";
  return "#059669";
}

export function Dashboard() {
  const { isDark } = useTheme();

  return (
    <div className="space-y-4 sm:space-y-5">
      {/* Row 1: KPI Metrics Row (5 compact cards) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-3.5">
        {kpiMetrics.map((m, i) => (
          <div
            key={m.label}
            className="anim-rise stagger rounded-xl border border-line bg-card p-3.5 sm:p-4 shadow-xs hover:shadow-md transition-all duration-200"
            style={{ "--i": i } as React.CSSProperties}
          >
            <div className="flex items-center justify-between mb-2">
              <div className={`w-8 h-8 sm:w-9 sm:h-9 rounded-lg ${m.iconBg} flex items-center justify-center ${m.iconColor}`}>
                <I name={m.icon} size={18} />
              </div>
              {m.emoji && <span className="text-[17px]">{m.emoji}</span>}
            </div>
            <p className="text-[11.5px] font-medium text-ink-faint truncate mb-0.5">{m.label}</p>
            <p className="text-[20px] font-bold text-ink leading-tight mb-1.5">
              {m.label === "Productivity Score" ? "78 / 100" : m.value}
            </p>
            <div className="h-7 mb-1.5">
              <Sparkline data={m.sparkline} color={m.sparkColor} height={28} />
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-ok font-medium truncate">{m.trend}</span>
              {m.secondary && (
                <span className="text-ink-faint text-[10px] hidden xl:inline truncate ml-1">{m.secondary}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Row 2: 3 Compact Cards (Productivity Trend | Time Allocation | Habit Overview) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 1. Productivity Trend Card */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display font-semibold text-[15px] text-ink">Productivity Trend</h3>
            <select className="text-[11.5px] font-medium text-ink-soft border border-line rounded-lg px-2.5 py-1 bg-card hover:bg-bg-soft transition-colors focus-ring cursor-pointer">
              <option>This Week</option>
              <option>Last Week</option>
              <option>This Month</option>
            </select>
          </div>
          <div className="h-[180px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={productivityTrend} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
                <defs>
                  <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={isDark ? "#7C6EED" : "#5B4CC4"} stopOpacity={0.25} />
                    <stop offset="100%" stopColor={isDark ? "#7C6EED" : "#5B4CC4"} stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="day"
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(day, idx) => `${day} ${12 + idx}`}
                  tick={{ fontSize: 10.5, fill: isDark ? "#9CA3AF" : "#6B7280" }}
                />
                <YAxis
                  domain={[0, 100]}
                  ticks={[0, 25, 50, 75, 100]}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 10.5, fill: isDark ? "#9CA3AF" : "#6B7280" }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: isDark ? "#181B26" : "#FFFFFF",
                    borderColor: isDark ? "#262B3B" : "#E5E7EB",
                    borderRadius: "8px",
                    color: isDark ? "#F3F4F6" : "#1F2937",
                    fontSize: "12px",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={isDark ? "#7C6EED" : "#5B4CC4"}
                  strokeWidth={2.2}
                  fillOpacity={1}
                  fill="url(#trendFill)"
                  dot={{ fill: isDark ? "#7C6EED" : "#5B4CC4", r: 3.5, strokeWidth: 0 }}
                  activeDot={{ r: 5, fill: isDark ? "#7C6EED" : "#5B4CC4" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 2. Time Allocation Card */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-display font-semibold text-[15px] text-ink">Time Allocation</h3>
          </div>
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 py-1">
            {/* Donut Chart with Center Label */}
            <div className="relative w-[140px] h-[140px] shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={timeAllocation}
                    cx="50%"
                    cy="50%"
                    innerRadius={42}
                    outerRadius={65}
                    paddingAngle={2}
                    dataKey="pct"
                  >
                    {timeAllocation.map((entry, index) => (
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
                <p className="text-[10px] uppercase font-semibold text-ink-faint tracking-wider">Total</p>
                <p className="text-[15px] font-bold text-ink">24h 30m</p>
              </div>
            </div>

            {/* Compact Legend */}
            <div className="flex-1 w-full space-y-1.5 min-w-0">
              {timeAllocation.map((t) => (
                <div key={t.label} className="flex items-center justify-between text-[11.5px]">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: t.color }} />
                    <span className="text-ink-soft truncate">{t.label}</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0 ml-1 font-mono">
                    <span className="font-semibold text-ink">{t.pct}%</span>
                    <span className="text-ink-faint text-[10px]">({t.time})</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 3. Habit Overview Card */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="font-display font-semibold text-[15px] text-ink">Habit Overview</h3>
              <select className="text-[11.5px] font-medium text-ink-soft border border-line rounded-lg px-2.5 py-1 bg-card hover:bg-bg-soft transition-colors focus-ring cursor-pointer">
                <option>This Week</option>
                <option>Last Week</option>
              </select>
            </div>

            {/* Table Header */}
            <div className="flex items-center justify-between text-[10.5px] font-semibold text-ink-faint uppercase tracking-wider pb-1.5 border-b border-line mb-2">
              <span>Habit</span>
              <div className="flex items-center gap-7">
                <span>Progress</span>
                <span className="w-12 text-right">Streak</span>
              </div>
            </div>

            {/* Habit Rows */}
            <div className="space-y-2">
              {habits.map((h) => {
                const pct = (h.completed / h.total) * 100;
                return (
                  <div key={h.name} className="flex items-center justify-between gap-2 text-[12px]">
                    <span className="font-medium text-ink truncate w-[100px] shrink-0">{h.name}</span>
                    <div className="flex items-center gap-2 flex-1 justify-end min-w-0">
                      <div className="w-16 sm:w-20 h-1.5 rounded-full bg-bg-soft overflow-hidden shrink-0">
                        <div
                          className="h-full rounded-full anim-bar"
                          style={{ width: `${pct}%`, background: "#10B981" }}
                        />
                      </div>
                      <span className="text-[11px] text-ink-faint tabular w-6 text-right shrink-0">
                        {h.completed}/{h.total}
                      </span>
                    </div>
                    <span className="text-[11.5px] font-medium text-ink tabular w-12 text-right shrink-0">
                      {h.streak} Days
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <button className="mt-2.5 text-[12px] font-semibold text-primary hover:text-primary-deep transition-colors text-left flex items-center gap-1">
            View all habits →
          </button>
        </div>
      </div>

      {/* Row 3: 3 Compact Cards (Activity Heatmap | Focus Sessions | Insights & Recommendations) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 1. Activity Heatmap Card */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-1.5">
                <h3 className="font-display font-semibold text-[15px] text-ink">Activity Heatmap</h3>
                <span title="Activity intensity distribution" className="text-ink-faint hover:text-ink cursor-pointer">
                  <I name="info" size={13} />
                </span>
              </div>
            </div>

            {/* Heatmap Grid */}
            <div className="overflow-x-auto pb-1">
              <div className="w-full">
                <div className="grid grid-cols-8 gap-1 mb-1 items-center">
                  <div className="w-9" />
                  {DAY_LABELS.map((d) => (
                    <div key={d} className="text-center text-[10px] font-semibold text-ink-faint">{d}</div>
                  ))}
                </div>
                {HEATMAP_LABELS.map((time, rowIdx) => (
                  <div key={time} className="grid grid-cols-8 gap-1 mb-1 items-center">
                    <div className="text-[9.5px] text-ink-faint text-right pr-1 font-mono">{time}</div>
                    {activityHeatmap.map((row, colIdx) => (
                      <div
                        key={`${rowIdx}-${colIdx}`}
                        className="aspect-square max-w-[24px] mx-auto w-full rounded-[3px] transition-transform hover:scale-110 cursor-pointer"
                        style={{ background: getHeatColor(row[rowIdx], isDark) }}
                        title={`${DAY_LABELS[colIdx]} ${time}: Level ${row[rowIdx]}`}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Heatmap Legend */}
          <div className="flex items-center justify-between pt-2 border-t border-line text-[10px] text-ink-faint mt-1">
            <span>Less Activity</span>
            <div className="flex items-center gap-1">
              {[0, 1, 2, 3, 4, 5].map((v) => (
                <div
                  key={v}
                  className="w-2.5 h-2.5 rounded-[2px]"
                  style={{ background: getHeatColor(v, isDark) }}
                />
              ))}
            </div>
            <span>More Activity</span>
          </div>
        </div>

        {/* 2. Focus Sessions Card */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="font-display font-semibold text-[15px] text-ink">Focus Sessions</h3>
              <select className="text-[11.5px] font-medium text-ink-soft border border-line rounded-lg px-2.5 py-1 bg-card hover:bg-bg-soft transition-colors focus-ring cursor-pointer">
                <option>This Week</option>
                <option>Last Week</option>
              </select>
            </div>

            {/* Top Mini Stats */}
            <div className="grid grid-cols-3 gap-2 mb-3">
              <div className="rounded-lg bg-bg-soft p-2 text-center">
                <p className="text-[10px] text-ink-faint">Sessions</p>
                <p className="text-[16px] font-bold text-ink leading-tight">14</p>
                <p className="text-[9.5px] text-ok font-medium">↑ 2 vs lw</p>
              </div>
              <div className="rounded-lg bg-bg-soft p-2 text-center">
                <p className="text-[10px] text-ink-faint">Avg. Focus</p>
                <p className="text-[16px] font-bold text-ink leading-tight">75m</p>
                <p className="text-[9.5px] text-ok font-medium">↑ 10 min</p>
              </div>
              <div className="rounded-lg bg-bg-soft p-2 text-center">
                <p className="text-[10px] text-ink-faint">Success</p>
                <p className="text-[16px] font-bold text-ink leading-tight">87%</p>
                <p className="text-[9.5px] text-ok font-medium">↑ 8%</p>
              </div>
            </div>

            {/* Recent Sessions */}
            <div className="space-y-1.5">
              {focusSessions.map((s) => (
                <div key={s.title} className="flex items-center justify-between gap-2 p-2 rounded-lg bg-bg-soft">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-6 h-6 rounded-md bg-primary-soft flex items-center justify-center text-primary shrink-0">
                      <I name="target" size={13} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-[11.5px] font-semibold text-ink truncate">{s.title}</p>
                      <p className="text-[10px] text-ink-faint truncate">{s.time}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10px] text-ink-faint font-mono">{s.duration}</span>
                    <span className="text-[9.5px] font-semibold text-ok bg-ok-soft px-1.5 py-0.5 rounded-full capitalize">
                      {s.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <button className="mt-2 text-[12px] font-semibold text-primary hover:text-primary-deep transition-colors text-left flex items-center gap-1">
            View all sessions →
          </button>
        </div>

        {/* 3. Insights & Recommendations Card */}
        <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="font-display font-semibold text-[15px] text-ink">Insights & Recommendations</h3>
            </div>
            <div className="space-y-2">
              {insights.map((ins, i) => {
                const toneMap = {
                  ok: { bg: "bg-ok-soft", text: "text-ok", icon: "ok" },
                  warn: { bg: "bg-warn-soft", text: "text-warn", icon: "alert" },
                  primary: { bg: "bg-primary-soft", text: "text-primary", icon: "trendUp" },
                  info: { bg: "bg-info-soft", text: "text-info", icon: "award" },
                };
                const t = toneMap[ins.tone];
                return (
                  <div key={i} className={`flex items-start gap-2.5 p-2 rounded-lg ${t.bg}`}>
                    <div className={`w-6 h-6 rounded-md ${t.bg} flex items-center justify-center ${t.text} shrink-0 mt-0.5`}>
                      <I name={ins.icon} size={13} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[11.5px] font-semibold text-ink leading-tight mb-0.5">{ins.title}</p>
                      <p className="text-[10.5px] text-ink-soft leading-snug line-clamp-2">{ins.body}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <button className="mt-2 text-[12px] font-semibold text-primary hover:text-primary-deep transition-colors text-left flex items-center gap-1">
            View full report →
          </button>
        </div>
      </div>

      {/* Row 4: Weekly Summary Card (Full Width) */}
      <div className="rounded-xl border border-line bg-card p-4 sm:p-5 shadow-xs">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
          {/* Summary Message with Trophy */}
          <div className="md:col-span-1 border-b md:border-b-0 md:border-r border-line pb-3 md:pb-0 md:pr-4">
            <div className="flex items-start gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-primary-soft text-primary flex items-center justify-center shrink-0">
                <I name="award" size={17} />
              </div>
              <div>
                <h4 className="font-display font-semibold text-[13.5px] text-ink leading-tight mb-1">Weekly Summary</h4>
                <p className="text-[11.5px] text-ink-soft leading-relaxed">{weeklySummary.message}</p>
              </div>
            </div>
          </div>

          {/* Top Productive Day */}
          <div className="rounded-lg bg-bg-soft p-3">
            <p className="text-[10.5px] text-ink-faint mb-0.5">Top Productive Day</p>
            <div className="flex items-baseline justify-between mb-1">
              <p className="text-[14px] font-bold text-ink">{weeklySummary.topDay.day}</p>
              <p className="text-[12px] font-semibold text-ok">{weeklySummary.topDay.score} / 100</p>
            </div>
            <div className="h-5">
              <Sparkline data={weeklySummary.topDay.sparkline} color="#2E9B57" height={20} />
            </div>
          </div>

          {/* Least Productive Day */}
          <div className="rounded-lg bg-bg-soft p-3">
            <p className="text-[10.5px] text-ink-faint mb-0.5">Least Productive Day</p>
            <div className="flex items-baseline justify-between mb-1">
              <p className="text-[14px] font-bold text-ink">{weeklySummary.leastDay.day}</p>
              <p className="text-[12px] font-semibold text-danger">{weeklySummary.leastDay.score} / 100</p>
            </div>
            <div className="h-5">
              <Sparkline data={weeklySummary.leastDay.sparkline} color="#EF4444" height={20} />
            </div>
          </div>

          {/* Weekly Goal Progress */}
          <div className="rounded-lg bg-bg-soft p-3">
            <p className="text-[10.5px] text-ink-faint mb-0.5">Weekly Goal Progress</p>
            <div className="flex items-baseline justify-between mb-1.5">
              <p className="text-[18px] font-bold text-ink leading-tight">{weeklySummary.goalProgress.current}%</p>
              <p className="text-[11px] text-ink-faint">Goal: {weeklySummary.goalProgress.target}%</p>
            </div>
            <div className="h-2 rounded-full bg-card overflow-hidden">
              <div
                className="h-full rounded-full anim-bar"
                style={{
                  width: `${(weeklySummary.goalProgress.current / weeklySummary.goalProgress.target) * 100}%`,
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
