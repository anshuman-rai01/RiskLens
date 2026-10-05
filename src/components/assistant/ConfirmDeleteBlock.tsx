import React from "react";
import { ConfirmDeleteBlock as ConfirmDeleteBlockType } from "../../lib/assistantTypes";
import { I } from "../icons";

interface ConfirmDeleteBlockProps {
  block: ConfirmDeleteBlockType;
  status?: "idle" | "deleting" | "deleted" | "cancelled" | "error";
  error?: string;
  onConfirm?: () => void;
  onCancel?: () => void;
}

export const ConfirmDeleteBlock: React.FC<ConfirmDeleteBlockProps> = ({
  block,
  status = "idle",
  error,
  onConfirm,
  onCancel,
}) => {
  const isIdle = status === "idle";
  const isDeleting = status === "deleting";
  const isDeleted = status === "deleted";
  const isCancelled = status === "cancelled";
  const isError = status === "error";

  const count = block.entry_ids?.length || 0;

  return (
    <div
      className={`w-full rounded-xl border bg-card overflow-hidden shadow-xs transition-all ${
        isDeleted
          ? "border-emerald-500/40 bg-emerald-500/[0.02]"
          : isCancelled
          ? "border-line opacity-60 bg-bg-soft"
          : isError
          ? "border-rose-500/40"
          : "border-rose-500/30 bg-rose-500/[0.02]"
      }`}
    >
      {/* Header */}
      <div className="px-3.5 py-2.5 border-b border-line bg-bg-soft flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md border border-rose-500/20 bg-rose-500/10 text-rose-600 dark:text-rose-400 flex items-center justify-center">
            <I name="alert" className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-semibold text-rose-700 dark:text-rose-400">
            Confirm Deletion
          </span>
        </div>

        {/* Status Badge */}
        {isDeleted && (
          <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
            <I name="check" className="w-3 h-3" /> Deleted
          </span>
        )}
        {isCancelled && (
          <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-black/5 dark:bg-white/5 text-ink-faint">
            Cancelled
          </span>
        )}
        {isDeleting && (
          <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400">
            <span className="w-2 h-2 rounded-full border-2 border-rose-500 border-t-transparent animate-spin" />
            Deleting...
          </span>
        )}
        {isError && (
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400">
            Failed
          </span>
        )}
        {isIdle && (
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-700 dark:text-rose-400">
            Destructive
          </span>
        )}
      </div>

      {/* Body */}
      <div className="p-3.5 space-y-2.5">
        <p className="text-xs font-medium text-ink leading-relaxed">
          {block.summary}
        </p>

        {/* Entries list preview */}
        {block.entries && block.entries.length > 0 && (
          <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
            {block.entries.map((entry, idx) => (
              <div
                key={entry.id || idx}
                className="flex items-center justify-between gap-2 p-2 rounded-lg bg-bg-soft/80 border border-line text-xs"
              >
                <div className="flex flex-col min-w-0">
                  <span className="font-medium text-ink truncate">
                    {entry.label || "Entry"}
                  </span>
                  <span className="text-[10px] text-ink-faint">
                    {entry.date} {entry.notes ? `• ${entry.notes}` : ""}
                  </span>
                </div>
                {entry.value && (
                  <span className="font-semibold text-rose-600 dark:text-rose-400 shrink-0 text-xs">
                    {entry.value}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Error message */}
        {isError && error && (
          <div className="text-[11px] font-medium text-rose-600 dark:text-rose-400 bg-rose-500/10 p-2 rounded-md">
            {error}
          </div>
        )}
      </div>

      {/* Footer Actions */}
      {!isDeleted && !isCancelled && (
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
              disabled={isDeleting}
              className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 transition-colors shadow-xs flex items-center gap-1.5"
            >
              <I name="x" className="w-3.5 h-3.5" />
              {isError
                ? "Retry Delete"
                : count > 1
                ? `Delete ${count} Entries`
                : "Delete Entry"}
            </button>
          )}
        </div>
      )}
    </div>
  );
};
