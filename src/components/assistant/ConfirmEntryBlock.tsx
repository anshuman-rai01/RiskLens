import React from "react";
import { ConfirmEntryBlock as ConfirmEntryBlockType } from "../../lib/assistantTypes";
import { I } from "../icons";

interface ConfirmEntryBlockProps {
  block: ConfirmEntryBlockType;
  status?: "idle" | "saving" | "saved" | "cancelled" | "error";
  error?: string;
  onConfirm?: () => void;
  onCancel?: () => void;
}

const CATEGORY_CONFIG: Record<
  string,
  { label: string; icon: string; accentClass: string }
> = {
  income_expense: {
    label: "Income & Expense",
    icon: "chart",
    accentClass: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20",
  },
  savings: {
    label: "Savings",
    icon: "calendar",
    accentClass: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  },
  study: {
    label: "Study",
    icon: "brain",
    accentClass: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
  },
  academic: {
    label: "Academic",
    icon: "target",
    accentClass: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
  },
  fitness: {
    label: "Fitness",
    icon: "activity",
    accentClass: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20",
  },
  habits: {
    label: "Habits",
    icon: "check",
    accentClass: "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20",
  },
};

export const ConfirmEntryBlock: React.FC<ConfirmEntryBlockProps> = ({
  block,
  status = "idle",
  error,
  onConfirm,
  onCancel,
}) => {
  const cat = CATEGORY_CONFIG[block.category] || {
    label: block.category.replace("_", " "),
    icon: "chart",
    accentClass: "bg-primary-500/10 text-primary-600 dark:text-primary-400 border-primary-500/20",
  };

  const isIdle = status === "idle";
  const isSaving = status === "saving";
  const isSaved = status === "saved";
  const isCancelled = status === "cancelled";
  const isError = status === "error";

  return (
    <div
      className={`w-full rounded-xl border bg-card overflow-hidden shadow-xs transition-all ${
        isSaved
          ? "border-emerald-500/40 bg-emerald-500/[0.02]"
          : isCancelled
          ? "border-line opacity-60 bg-bg-soft"
          : isError
          ? "border-rose-500/40"
          : "border-line"
      }`}
    >
      {/* Header */}
      <div className="px-3.5 py-2.5 border-b border-line bg-bg-soft flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div
            className={`w-6 h-6 rounded-md border flex items-center justify-center ${cat.accentClass}`}
          >
            <I name={cat.icon} className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-semibold text-ink">
            Propose: {cat.label}
          </span>
        </div>

        {/* Status Badge */}
        {isSaved && (
          <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
            <I name="check" className="w-3 h-3" /> Saved
          </span>
        )}
        {isCancelled && (
          <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-black/5 dark:bg-white/5 text-ink-faint">
            Cancelled
          </span>
        )}
        {isSaving && (
          <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-primary-500/10 text-primary-600 dark:text-primary-400">
            <span className="w-2 h-2 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" />
            Saving...
          </span>
        )}
        {isError && (
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400">
            Failed
          </span>
        )}
        {isIdle && (
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-400">
            Pending
          </span>
        )}
      </div>

      {/* Body */}
      <div className="p-3.5 space-y-2.5">
        <p className="text-xs font-medium text-ink leading-relaxed">
          {block.summary}
        </p>

        {/* Preview Key-Values */}
        {block.preview && Object.keys(block.preview).length > 0 && (
          <div className="grid grid-cols-2 gap-1.5 p-2 rounded-lg bg-bg-soft/70 border border-line text-[11px]">
            {Object.entries(block.preview).map(([key, value]) => (
              <div key={key} className="flex flex-col">
                <span className="text-[10px] font-semibold text-ink-faint uppercase tracking-wider">
                  {key}
                </span>
                <span className="font-medium text-ink truncate" title={String(value)}>
                  {String(value)}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Error message if save failed */}
        {isError && error && (
          <div className="text-[11px] font-medium text-rose-600 dark:text-rose-400 bg-rose-500/10 p-2 rounded-md">
            {error}
          </div>
        )}
      </div>

      {/* Footer Actions */}
      {!isSaved && !isCancelled && (
        <div className="px-3.5 py-2.5 border-t border-line bg-bg-soft flex items-center justify-end gap-2">
          {isIdle && onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold text-ink-faint hover:text-ink hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            >
              Cancel
            </button>
          )}

          {isError && onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold text-ink-faint hover:text-ink transition-colors"
            >
              Dismiss
            </button>
          )}

          {(isIdle || isError) && onConfirm && (
            <button
              type="button"
              onClick={onConfirm}
              disabled={isSaving}
              className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-gradient-primary hover:opacity-95 transition-opacity shadow-xs flex items-center gap-1.5"
            >
              <I name="check" className="w-3.5 h-3.5" />
              {isError ? "Retry Save" : "Save Entry"}
            </button>
          )}
        </div>
      )}
    </div>
  );
};
