import React from "react";
import { MetricsBlock as MetricsBlockType, MetricItemTone } from "../../lib/assistantTypes";
import { formatCurrency } from "../../lib/currency";

interface MetricsBlockProps {
  block: MetricsBlockType;
}

function formatValue(value: number, format: "currency" | "number" | "percent"): string {
  if (format === "currency") {
    return formatCurrency(value);
  }
  if (format === "percent") {
    return `${value.toFixed(1)}%`;
  }
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function getToneClass(tone?: MetricItemTone): string {
  switch (tone) {
    case "ok":
      return "text-emerald-600 dark:text-emerald-400";
    case "danger":
      return "text-rose-600 dark:text-rose-400";
    case "warn":
      return "text-amber-600 dark:text-amber-400";
    case "neutral":
    default:
      return "text-ink";
  }
}

export const MetricsBlock: React.FC<MetricsBlockProps> = ({ block }) => {
  if (!block.items || block.items.length === 0) return null;

  return (
    <div className="w-full space-y-2">
      {block.title && (
        <h4 className="text-xs font-semibold text-ink-soft uppercase tracking-wider">
          {block.title}
        </h4>
      )}
      <div
        className={`grid gap-2 ${
          block.items.length === 1
            ? "grid-cols-1"
            : block.items.length === 2
            ? "grid-cols-2"
            : "grid-cols-2 sm:grid-cols-3"
        }`}
      >
        {block.items.map((item, idx) => (
          <div
            key={idx}
            className="p-2.5 rounded-lg bg-bg-soft border border-line flex flex-col justify-between"
          >
            <div className="text-[11px] font-medium text-ink-faint truncate" title={item.label}>
              {item.label}
            </div>
            <div className={`text-sm font-semibold tracking-tight mt-1 truncate ${getToneClass(item.tone)}`}>
              {formatValue(item.value, item.format)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
