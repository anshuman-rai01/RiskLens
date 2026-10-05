import React, { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  BarChart,
  Bar,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";
import { format, parseISO } from "date-fns";

import { ChartBlock as ChartBlockType, ChartSeriesRole } from "../../lib/assistantTypes";
import { formatCurrency } from "../../lib/currency";
import { formatCompactINR } from "../../lib/format";
import { useTheme } from "../../state/ThemeContext";

interface ChartBlockProps {
  block: ChartBlockType;
}

const ROLE_COLORS: Record<ChartSeriesRole, { light: string; dark: string }> = {
  income: { light: "#16A34A", dark: "#34D399" },
  expense: { light: "#DC2626", dark: "#FB7185" },
  savings: { light: "#5B4CC4", dark: "#A855F7" },
  forecast: { light: "#0284C7", dark: "#38BDF8" },
  neutral: { light: "#64748B", dark: "#94A3B8" },
};

export const ChartBlock: React.FC<ChartBlockProps> = ({ block }) => {
  const { isDark } = useTheme();

  // Defensive validation: ensure data and series exist
  if (!block || !Array.isArray(block.data) || block.data.length === 0 || !Array.isArray(block.series) || block.series.length === 0) {
    return null;
  }

  // Precompute data with range bands if band keys are defined
  const chartData = useMemo(() => {
    return block.data.map((row) => {
      if (!row || typeof row !== "object" || !("x" in row)) {
        return null;
      }
      const newRow: Record<string, any> = { ...row };
      if (block.band && block.band.lower_key in row && block.band.upper_key in row) {
        newRow["_band"] = [
          Number(row[block.band.lower_key]) || 0,
          Number(row[block.band.upper_key]) || 0,
        ];
      }
      return newRow;
    }).filter(Boolean) as Record<string, any>[];
  }, [block.data, block.band]);

  if (chartData.length === 0) {
    return null;
  }

  const formatX = (val: string) => {
    if (!val) return "";
    if (block.x_format === "date") {
      try {
        return format(parseISO(val), "d MMM");
      } catch {
        return val;
      }
    }
    // Category tick truncation
    return val.length > 10 ? `${val.slice(0, 8)}…` : val;
  };

  const formatY = (val: number) => {
    if (block.y_format === "currency") {
      return formatCompactINR(val);
    }
    return val.toLocaleString("en-IN");
  };

  const gridStroke = isDark ? "#334155" : "#E2E8F0";
  const textFill = isDark ? "#94A3B8" : "#64748B";

  return (
    <div
      className="w-full bg-bg-soft border border-line rounded-lg p-3 space-y-2"
      aria-label={block.title}
    >
      <div className="flex flex-col">
        <h4 className="text-xs font-semibold text-ink truncate" title={block.title}>
          {block.title}
        </h4>
        {block.subtitle && (
          <span className="text-[11px] text-ink-faint truncate">{block.subtitle}</span>
        )}
      </div>

      <div className="w-full h-[200px]">
        <ResponsiveContainer width="100%" height="100%">
          {block.kind === "bar" ? (
            <BarChart data={chartData} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} opacity={0.6} />
              <XAxis
                dataKey="x"
                tickFormatter={formatX}
                tick={{ fill: textFill, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: gridStroke }}
              />
              <YAxis
                tickFormatter={formatY}
                tick={{ fill: textFill, fontSize: 10 }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: isDark ? "#0F172A" : "#FFFFFF",
                  borderColor: isDark ? "#334155" : "#E2E8F0",
                  borderRadius: "8px",
                  fontSize: "11px",
                  color: isDark ? "#F8FAFC" : "#0F172A",
                }}
                formatter={(val: any, name: any) => [
                  block.y_format === "currency" ? formatCurrency(Number(val)) : Number(val).toLocaleString("en-IN"),
                  name,
                ]}
                labelFormatter={(lbl: any) => (block.x_format === "date" ? formatX(String(lbl)) : String(lbl))}
              />
              <Legend
                wrapperStyle={{ fontSize: "11px", paddingTop: "6px" }}
              />
              {block.series.map((s) => {
                const colors = ROLE_COLORS[s.role] || ROLE_COLORS.neutral;
                const fill = isDark ? colors.dark : colors.light;
                return (
                  <Bar
                    key={s.key}
                    dataKey={s.key}
                    name={s.label}
                    fill={fill}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={36}
                  />
                );
              })}
            </BarChart>
          ) : (
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} opacity={0.6} />
              <XAxis
                dataKey="x"
                tickFormatter={formatX}
                tick={{ fill: textFill, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: gridStroke }}
              />
              <YAxis
                tickFormatter={formatY}
                tick={{ fill: textFill, fontSize: 10 }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: isDark ? "#0F172A" : "#FFFFFF",
                  borderColor: isDark ? "#334155" : "#E2E8F0",
                  borderRadius: "8px",
                  fontSize: "11px",
                  color: isDark ? "#F8FAFC" : "#0F172A",
                }}
                formatter={(val: any, name: any) => [
                  block.y_format === "currency" ? formatCurrency(Number(val)) : Number(val).toLocaleString("en-IN"),
                  name,
                ]}
                labelFormatter={(lbl: any) => (block.x_format === "date" ? formatX(String(lbl)) : String(lbl))}
              />
              <Legend
                wrapperStyle={{ fontSize: "11px", paddingTop: "6px" }}
              />
              {/* Range Area behind lines */}
              {block.band && (
                <Area
                  type="monotone"
                  dataKey="_band"
                  name="Confidence Range"
                  stroke="none"
                  fill={isDark ? "#38BDF8" : "#0284C7"}
                  fillOpacity={0.18}
                  isAnimationActive={false}
                />
              )}
              {block.series.map((s) => {
                const colors = ROLE_COLORS[s.role] || ROLE_COLORS.neutral;
                const stroke = isDark ? colors.dark : colors.light;
                return (
                  <Line
                    key={s.key}
                    type="monotone"
                    dataKey={s.key}
                    name={s.label}
                    stroke={stroke}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                );
              })}
            </ComposedChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
};
