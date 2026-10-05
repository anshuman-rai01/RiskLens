import React from "react";
import { Block } from "../../lib/assistantTypes";
import { MetricsBlock } from "./MetricsBlock";
import { ChartBlock } from "./ChartBlock";
import { NoticeBlock } from "./NoticeBlock";
import { TableBlock } from "./TableBlock";
import { ConfirmEntryBlock } from "./ConfirmEntryBlock";
import { ConfirmEntryBlock as ConfirmEntryBlockType, ConfirmDeleteBlock as ConfirmDeleteBlockType } from "../../lib/assistantTypes";

interface BlockRendererProps {
  block: Block;
  entryStatus?: "idle" | "saving" | "saved" | "cancelled" | "error";
  entryError?: string;
  onConfirmEntry?: (block: ConfirmEntryBlockType) => void;
  onCancelEntry?: (block: ConfirmEntryBlockType) => void;
  deleteStatus?: "idle" | "deleting" | "deleted" | "cancelled" | "error";
  deleteError?: string;
  onConfirmDelete?: (block: ConfirmDeleteBlockType) => void;
  onCancelDelete?: (block: ConfirmDeleteBlockType) => void;
}

/**
 * Registry mapping block type strings to their respective React components.
 * Extensible: Adding a new block type only requires registering a component here.
 */
const BLOCK_REGISTRY: Record<string, React.ComponentType<{ block: any }>> = {
  metrics: MetricsBlock,
  chart: ChartBlock,
  notice: NoticeBlock,
  table: TableBlock,
};

export const BlockRenderer: React.FC<BlockRendererProps> = ({
  block,
  entryStatus,
  entryError,
  onConfirmEntry,
  onCancelEntry,
  deleteStatus,
  deleteError,
  onConfirmDelete,
  onCancelDelete,
}) => {
  if (!block || typeof block !== "object" || !block.type) {
    return null;
  }

  if (block.type === "confirm_entry") {
    return (
      <div className="w-full my-1">
        <ConfirmEntryBlock
          block={block as ConfirmEntryBlockType}
          status={entryStatus}
          error={entryError}
          onConfirm={onConfirmEntry ? () => onConfirmEntry(block as ConfirmEntryBlockType) : undefined}
          onCancel={onCancelEntry ? () => onCancelEntry(block as ConfirmEntryBlockType) : undefined}
        />
      </div>
    );
  }

  const Component = BLOCK_REGISTRY[block.type];

  // If unknown block type, render nothing without crashing
  if (!Component) {
    return null;
  }

  return (
    <div className="w-full my-1">
      <Component block={block} />
    </div>
  );
};
