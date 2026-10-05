/**
 * TypeScript types for the RiskLens AI Assistant.
 * Strictly mirrors the backend snake_case JSON schemas and Block discriminated union.
 */

export type MetricItemTone = "neutral" | "ok" | "warn" | "danger";
export type MetricItemFormat = "currency" | "number" | "percent";

export interface MetricItem {
  label: string;
  value: number;
  format: MetricItemFormat;
  tone?: MetricItemTone;
}

export interface MetricsBlock {
  type: "metrics";
  id: string;
  title?: string | null;
  items: MetricItem[];
}

export type ChartSeriesRole = "income" | "expense" | "savings" | "forecast" | "neutral";

export interface ChartSeries {
  key: string;
  label: string;
  role: ChartSeriesRole;
}

export interface ChartBand {
  lower_key: string;
  upper_key: string;
}

export interface ChartBlock {
  type: "chart";
  id: string;
  title: string;
  subtitle?: string | null;
  kind: "line" | "bar";
  x_format: "date" | "category";
  y_format: "currency" | "number";
  series: ChartSeries[];
  band?: ChartBand | null;
  data: Record<string, any>[];
}

export interface NoticeBlock {
  type: "notice";
  id: string;
  tone: "info" | "warn";
  text: string;
}

/**
 * Generic extensible block representation.
 * Known types are MetricsBlock, ChartBlock, NoticeBlock.
 * Unknown types must not crash the renderer (rendered as null).
 */
export type KnownBlock = MetricsBlock | ChartBlock | NoticeBlock;

export interface UnknownBlock {
  type: string;
  id: string;
  [key: string]: any;
}

export type Block = KnownBlock | UnknownBlock;

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

export interface AssistantChatRequest {
  messages: ChatMessage[];
  client_date?: string;
}

export interface AssistantChatResponse {
  id: string;
  text: string;
  blocks: Block[];
  outcome: "ok" | "degraded" | "unavailable";
}

export interface AssistantMessageState {
  id: string;
  role: "user" | "assistant";
  text: string;
  blocks?: Block[];
  outcome?: "ok" | "degraded" | "unavailable";
  isError?: boolean;
}
