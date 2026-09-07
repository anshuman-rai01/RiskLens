import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { I } from "./icons";
import { Sparkline } from "./ui";
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

function getHeatColor(value: number): string {
  if (value === 0) return "#F3F4F6";
  if (value === 1) return "#D1FAE5";
  if (value === 2) return "#6EE7B7";
  if (value === 3) return "#34D399";
  if (value === 4) return "#10B981";
  return "#059669";
}

export function Dashboard() {
  return (
    <div className="space-y-6">
      {/* KPI Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {kpiMetrics.map((m, i) => (
          <div
            key={m.label}
            className="anim-rise stagger rounded-xl border border-line bg-card p-4 shadow-sm hover:shadow-md transition-shadow"
            style={{ "--i": i } as React.CSSProperties}
          >
            <div className="flex items-start justify-between mb-3">
              <div className={`w-10 h-10 rounded-lg ${m.iconBg} flex items-center justify-center ${m.iconColor}`}>
                <I name={m.icon} size={20} />
              </div>
              {m.emoji && <span className="text-[20px]">{m.emoji}</span>}
            </div>
            <p className="text-[12px] font-medium text-ink-faint mb-1">{m.label}</p>
            <p className="text-[22px] font-bold text-ink leading-tight mb-2">{m.value}</p>
            <div className="h-8 mb-2">
              <Sparkline data={m.sparkline} color={m.sparkColor} height={32} />
            </div>
            <p className="text-[11.5px] text-ok font-medium">{m.trend}</p>
            {m.secondary && <p className="text-[11px] text-ink-faint mt-0.5">{m.secondary}</p>}
          </div>
        ))}
      </div>

      {/* Analytics Grid */}
      <div className="grid lg:grid-cols-3 gap-5">
        {/* Productivity Trend */}
        <div className="lg:col-span-2 rounded-xl border border-line bg-card p-5 shadow-sm">
          <div className="flex items-center justify-between mb-5">
            <h3 className="font-display font-semibold text-[16px] text-ink">Productivity Trend</h3>
            <select className="text-[12.5px] font-medium text-ink-soft border border-line rounded-lg px-3 py-1.5 bg-card focus-ring">
              <option>This Week</option>
              <option>Last Week</option>
              <option>This Month</option>
            </select>
          </div>
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={productivityTrend}>
                <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "#6B7280" }} />
                <YAxis domain={[0, 100]} axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "#6B7280" }} />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#5B4CC4"
                  strokeWidth={2.5}
                  dot={{ fill: "#5B4CC4", r: 4, strokeWidth: 0 }}
                  activeDot={{ r: 6, fill: "#5B4CC4" }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Time Allocation */}
        <div className="rounded-xl border border-line bg-card p-5 shadow-sm">
          <h3 className="font-display font-semibold text-[16px] text-ink mb-5">Time Allocation</h3>
          <div className="relative h-[180px] mb-4">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={timeAllocation}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={80}
                  paddingAngle={2}
                  dataKey="pct"
                >
                  {timeAllocation.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <p className="text-[11px] text-ink-faint">Total</p>
              <p className="text-[18px] font-bold text-ink">24h 30m</p>
            </div>
          </div>
          <div className="space-y-2">
            {timeAllocation.map((t) => (
              <div key={t.label} className="flex items-center justify-between text-[12.5px]">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: t.color }} />
                  <span className="text-ink-soft">{t.label}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-ink">{t.pct}%</span>
                  <span className="text-ink-faint text-[11px]">{t.time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Activity / Focus Grid */}
      <div className="grid lg:grid-cols-2 gap-5">
        {/* Habit Overview */}
        <div className="rounded-xl border border-line bg-card p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display font-semibold text-[16px] text-ink">Habit Overview</h3>
            <select className="text-[12.5px] font-medium text-ink-soft border border-line rounded-lg px-3 py-1.5 bg-card focus-ring">
              <option>This Week</option>
              <option>Last Week</option>
            </select>
          </div>
          <div className="space-y-3">
            {habits.map((h) => {
              const pct = (h.completed / h.total) * 100;
              return (
                <div key={h.name} className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[13px] font-medium text-ink truncate">{h.name}</span>
                      <span className="text-[12px] text-ink-faint tabular">{h.completed} / {h.total}</span>
                    </div>
                    <div className="h-2 rounded-full bg-bg-soft overflow-hidden">
                      <div
                        className="h-full rounded-full anim-bar"
                        style={{ width: `${pct}%`, background: h.color }}
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <I name="flame" size={14} className="text-danger" />
                    <span className="text-[12px] font-semibold text-ink tabular">{h.streak} Days</span>
                  </div>
                </div>
              );
            })}
          </div>
          <button className="mt-4 text-[13px] font-semibold text-primary hover:text-primary-deep transition-colors">
            View all habits →
          </button>
        </div>

        {/* Activity Heatmap */}
        <div className="rounded-xl border border-line bg-card p-5 shadow-sm">
          <h3 className="font-display font-semibold text-[16px] text-ink mb-4">Activity Heatmap</h3>
          <div className="overflow-x-auto">
            <div className="min-w-[400px]">
              <div className="grid grid-cols-7 gap-1.5 mb-2">
                {DAY_LABELS.map((d) => (
                  <div key={d} className="text-center text-[10.5px] font-medium text-ink-faint">{d}</div>
                ))}
              </div>
              {HEATMAP_LABELS.map((time, rowIdx) => (
                <div key={time} className="grid grid-cols-7 gap-1.5 mb-1.5 items-center">
                  <div className="text-[10.5px] text-ink-faint text-right pr-1">{time}</div>
                  {activityHeatmap.map((row, colIdx) => (
                    <div
                      key={`${rowIdx}-${colIdx}`}
                      className="aspect-square rounded-sm transition-colors"
                      style={{ background: getHeatColor(row[rowIdx]) }}
                      title={`${DAY_LABELS[colIdx]} ${time}: intensity ${row[rowIdx]}`}
                    />
                  ))}
                </div>
              ))}
              <div className="flex items-center justify-end gap-1.5 mt-3">
                <span className="text-[10px] text-ink-faint">Less</span>
                {[0, 1, 2, 3, 4, 5].map((v) => (
                  <div key={v} className="w-3 h-3 rounded-sm" style={{ background: getHeatColor(v) }} />
                ))}
                <span className="text-[10px] text-ink-faint">More</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Focus Sessions & Insights */}
      <div className="grid lg:grid-cols-2 gap-5">
        {/* Focus Sessions */}
        <div className="rounded-xl border border-line bg-card p-5 shadow-sm">
          <h3 className="font-display font-semibold text-[16px] text-ink mb-4">Focus Sessions</h3>
          <div className="grid grid-cols-3 gap-3 mb-5">
            <div className="rounded-lg bg-bg-soft p-3">
              <p className="text-[11px] text-ink-faint mb-1">Sessions</p>
              <p className="text-[18px] font-bold text-ink">14</p>
              <p className="text-[10.5px] text-ok font-medium">↑ 2 vs last week</p>
            </div>
            <div className="rounded-lg bg-bg-soft p-3">
              <p className="text-[11px] text-ink-faint mb-1">Avg. Focus Time</p>
              <p className="text-[18px] font-bold text-ink">75 min</p>
              <p className="text-[10.5px] text-ok font-medium">↑ 10 min</p>
            </div>
            <div className="rounded-lg bg-bg-soft p-3">
              <p className="text-[11px] text-ink-faint mb-1">Success Rate</p>
              <p className="text-[18px] font-bold text-ink">87%</p>
              <p className="text-[10.5px] text-ok font-medium">↑ 8%</p>
            </div>
          </div>
          <div className="space-y-3">
            {focusSessions.map((s) => (
              <div key={s.title} className="flex items-center gap-3 p-3 rounded-lg bg-bg-soft">
                <div className="w-9 h-9 rounded-lg bg-primary-soft flex items-center justify-center text-primary shrink-0">
                  <I name="target" size={16} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] font-semibold text-ink truncate">{s.title}</p>
                  <p className="text-[11.5px] text-ink-faint">{s.time} · {s.duration}</p>
                </div>
                <span className="text-[11px] font-semibold text-ok bg-ok-soft px-2 py-0.5 rounded-full">
                  {s.status}
                </span>
              </div>
            ))}
          </div>
          <button className="mt-4 text-[13px] font-semibold text-primary hover:text-primary-deep transition-colors">
            View all sessions →
          </button>
        </div>

        {/* Insights & Recommendations */}
        <div className="rounded-xl border border-line bg-card p-5 shadow-sm">
          <h3 className="font-display font-semibold text-[16px] text-ink mb-4">Insights & Recommendations</h3>
          <div className="space-y-3">
            {insights.map((ins, i) => {
              const toneMap = {
                ok: { bg: "bg-ok-soft", text: "text-ok", icon: "ok" },
                warn: { bg: "bg-warn-soft", text: "text-warn", icon: "alert" },
                primary: { bg: "bg-primary-soft", text: "text-primary", icon: "trendUp" },
                info: { bg: "bg-info-soft", text: "text-info", icon: "award" },
              };
              const t = toneMap[ins.tone];
              return (
                <div key={i} className={`flex gap-3 p-3 rounded-lg ${t.bg}`}>
                  <div className={`w-8 h-8 rounded-lg ${t.bg} flex items-center justify-center ${t.text} shrink-0`}>
                    <I name={ins.icon} size={16} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] font-semibold text-ink mb-0.5">{ins.title}</p>
                    <p className="text-[12px] text-ink-soft leading-relaxed">{ins.body}</p>
                  </div>
                </div>
              );
            })}
          </div>
          <button className="mt-4 text-[13px] font-semibold text-primary hover:text-primary-deep transition-colors">
            View full report →
          </button>
        </div>
      </div>

      {/* Weekly Summary */}
      <div className="rounded-xl border border-line bg-card p-5 shadow-sm">
        <h3 className="font-display font-semibold text-[16px] text-ink mb-4">Weekly Summary</h3>
        <p className="text-[13.5px] text-ink-soft mb-5">{weeklySummary.message}</p>
        <div className="grid md:grid-cols-4 gap-4">
          <div className="rounded-lg bg-bg-soft p-4">
            <p className="text-[11px] text-ink-faint mb-1">Top Productive Day</p>
            <p className="text-[16px] font-bold text-ink mb-1">{weeklySummary.topDay.day}</p>
            <p className="text-[13px] font-semibold text-ok">{weeklySummary.topDay.score} / 100</p>
            <div className="h-6 mt-2">
              <Sparkline data={weeklySummary.topDay.sparkline} color="#2E9B57" height={24} />
            </div>
          </div>
          <div className="rounded-lg bg-bg-soft p-4">
            <p className="text-[11px] text-ink-faint mb-1">Least Productive Day</p>
            <p className="text-[16px] font-bold text-ink mb-1">{weeklySummary.leastDay.day}</p>
            <p className="text-[13px] font-semibold text-danger">{weeklySummary.leastDay.score} / 100</p>
            <div className="h-6 mt-2">
              <Sparkline data={weeklySummary.leastDay.sparkline} color="#EF4444" height={24} />
            </div>
          </div>
          <div className="rounded-lg bg-bg-soft p-4 md:col-span-2">
            <p className="text-[11px] text-ink-faint mb-1">Weekly Goal Progress</p>
            <div className="flex items-baseline justify-between mb-2">
              <p className="text-[22px] font-bold text-ink">{weeklySummary.goalProgress.current}%</p>
              <p className="text-[12px] text-ink-faint">Goal: {weeklySummary.goalProgress.target}%</p>
            </div>
            <div className="h-3 rounded-full bg-white overflow-hidden">
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
