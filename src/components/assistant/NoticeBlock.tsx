import React from "react";
import { NoticeBlock as NoticeBlockType } from "../../lib/assistantTypes";
import { I } from "../icons";

interface NoticeBlockProps {
  block: NoticeBlockType;
}

export const NoticeBlock: React.FC<NoticeBlockProps> = ({ block }) => {
  const isWarn = block.tone === "warn";

  return (
    <div
      className={`flex items-start gap-2.5 p-3 rounded-lg text-xs leading-relaxed border ${
        isWarn
          ? "bg-amber-500/10 border-amber-500/30 text-amber-900 dark:text-amber-200"
          : "bg-sky-500/10 border-sky-500/30 text-sky-900 dark:text-sky-200"
      }`}
      role="status"
    >
      <I
        name={isWarn ? "alert" : "info"}
        className={`w-4 h-4 mt-0.5 shrink-0 ${
          isWarn ? "text-amber-600 dark:text-amber-400" : "text-sky-600 dark:text-sky-400"
        }`}
      />
      <div className="flex-1 font-medium">{block.text}</div>
    </div>
  );
};
