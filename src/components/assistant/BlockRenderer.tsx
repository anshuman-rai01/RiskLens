import React from "react";
import { Block } from "../../lib/assistantTypes";
import { MetricsBlock } from "./MetricsBlock";
import { ChartBlock } from "./ChartBlock";
import { NoticeBlock } from "./NoticeBlock";
import { TableBlock } from "./TableBlock";

interface BlockRendererProps {
  block: Block;
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

export const BlockRenderer: React.FC<BlockRendererProps> = ({ block }) => {
  if (!block || typeof block !== "object" || !block.type) {
    return null;
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
