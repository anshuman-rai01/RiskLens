import React from "react";
import { TableBlock as TableBlockType } from "../../lib/assistantTypes";

interface TableBlockProps {
  block: TableBlockType;
}

export const TableBlock: React.FC<TableBlockProps> = ({ block }) => {
  if (!block.columns || block.columns.length === 0 || !block.rows) {
    return null;
  }

  const getAlignClass = (align?: "left" | "right" | "center") => {
    switch (align) {
      case "right":
        return "text-right";
      case "center":
        return "text-center";
      case "left":
      default:
        return "text-left";
    }
  };

  return (
    <div className="w-full rounded-xl border border-line bg-card overflow-hidden shadow-xs">
      {/* Table Header */}
      <div className="px-3 py-2 border-b border-line bg-bg-soft flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold text-ink truncate">
          {block.title}
        </h4>
        {typeof block.total_count === "number" && (
          <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-primary-500/10 text-primary-600 dark:text-primary-400 shrink-0">
            {block.rows.length < block.total_count
              ? `Showing ${block.rows.length} of ${block.total_count}`
              : `${block.total_count} ${block.total_count === 1 ? "entry" : "entries"}`}
          </span>
        )}
      </div>

      {/* Table Content */}
      <div className="overflow-x-auto max-h-60 overflow-y-auto">
        <table className="w-full text-xs text-left border-collapse">
          <thead className="bg-bg-soft/70 sticky top-0 z-10 backdrop-blur-xs">
            <tr>
              {block.columns.map((col) => (
                <th
                  key={col.key}
                  className={`px-3 py-1.5 text-[10px] font-semibold text-ink-faint uppercase tracking-wider ${getAlignClass(
                    col.align
                  )}`}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {block.rows.length === 0 ? (
              <tr>
                <td
                  colSpan={block.columns.length}
                  className="px-3 py-4 text-center text-xs text-ink-faint"
                >
                  No entries to display.
                </td>
              </tr>
            ) : (
              block.rows.map((row, rowIdx) => (
                <tr
                  key={row.id || rowIdx}
                  className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition-colors"
                >
                  {block.columns.map((col) => (
                    <td
                      key={col.key}
                      className={`px-3 py-2 whitespace-nowrap text-xs text-ink ${getAlignClass(
                        col.align
                      )}`}
                    >
                      {row[col.key] !== undefined && row[col.key] !== null
                        ? String(row[col.key])
                        : "—"}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
