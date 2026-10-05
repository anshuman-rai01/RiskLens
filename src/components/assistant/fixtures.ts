/**
 * Test fixtures for verifying UI Block rendering across all states.
 */

import { AssistantChatResponse } from "../../lib/assistantTypes";

export const FIXTURE_RESPONSES: Record<string, AssistantChatResponse> = {
  forecast_single: {
    id: "fix_fc_1",
    text: "Here is your 30-day expense forecast based on historical tracking. Missing days were treated as zero-expense days.",
    outcome: "ok",
    blocks: [
      {
        type: "notice",
        id: "blk_not_1",
        tone: "info",
        text: "Rough estimate: based on 22 days of entries.",
      },
      {
        type: "metrics",
        id: "blk_met_1",
        title: "Expense Forecast Summary",
        items: [
          { label: "Predicted Total", value: 14500, format: "currency", tone: "neutral" },
          { label: "Daily Average", value: 483.33, format: "currency", tone: "neutral" },
          { label: "Past 30d Actual", value: 15200, format: "currency", tone: "neutral" },
        ],
      },
      {
        type: "chart",
        id: "blk_cht_1",
        title: "Expenses Forecast (30 Days)",
        subtitle: "Daily projections with 80% confidence interval",
        kind: "line",
        x_format: "date",
        y_format: "currency",
        series: [{ key: "predicted", label: "Predicted", role: "forecast" }],
        band: { lower_key: "lower", upper_key: "upper" },
        data: [
          { x: "2026-10-05", predicted: 450, lower: 380, upper: 520 },
          { x: "2026-10-06", predicted: 510, lower: 420, upper: 600 },
          { x: "2026-10-07", predicted: 480, lower: 400, upper: 560 },
          { x: "2026-10-08", predicted: 550, lower: 460, upper: 640 },
          { x: "2026-10-09", predicted: 600, lower: 500, upper: 700 },
          { x: "2026-10-10", predicted: 520, lower: 430, upper: 610 },
          { x: "2026-10-11", predicted: 490, lower: 410, upper: 580 },
        ],
      },
    ],
  },

  finances_two_line: {
    id: "fix_fin_1",
    text: "Here is your overall financial outlook combining expected income and expenses for the upcoming month.",
    outcome: "ok",
    blocks: [
      {
        type: "metrics",
        id: "blk_met_2",
        title: "Finances Outlook Summary",
        items: [
          { label: "Expected Expenses", value: 32000, format: "currency", tone: "neutral" },
          { label: "Expected Income", value: 55000, format: "currency", tone: "ok" },
          { label: "Expected Net", value: 23000, format: "currency", tone: "ok" },
        ],
      },
      {
        type: "chart",
        id: "blk_cht_2",
        title: "Finances Projection (30 Days)",
        subtitle: "Income vs Expenses trajectory",
        kind: "line",
        x_format: "date",
        y_format: "currency",
        series: [
          { key: "income", label: "Income", role: "income" },
          { key: "expense", label: "Expenses", role: "expense" },
        ],
        data: [
          { x: "2026-10-05", income: 1800, expense: 950 },
          { x: "2026-10-06", income: 1800, expense: 1200 },
          { x: "2026-10-07", income: 1800, expense: 1100 },
          { x: "2026-10-08", income: 1800, expense: 800 },
          { x: "2026-10-09", income: 1800, expense: 1500 },
          { x: "2026-10-10", income: 1800, expense: 900 },
          { x: "2026-10-11", income: 1800, expense: 1050 },
        ],
      },
    ],
  },

  report_bars: {
    id: "fix_rep_1",
    text: "Here is your financial report for the past week. You had a net positive cash flow.",
    outcome: "ok",
    blocks: [
      {
        type: "metrics",
        id: "blk_met_3",
        title: "Financial Summary (Past 7 Days)",
        items: [
          { label: "Income", value: 25000, format: "currency", tone: "ok" },
          { label: "Expenses", value: 8400, format: "currency", tone: "danger" },
          { label: "Net", value: 16600, format: "currency", tone: "ok" },
          { label: "Savings Added", value: 5000, format: "currency", tone: "neutral" },
        ],
      },
      {
        type: "chart",
        id: "blk_cht_3",
        title: "Daily Income vs Expenses",
        kind: "bar",
        x_format: "date",
        y_format: "currency",
        series: [
          { key: "income", label: "Income", role: "income" },
          { key: "expense", label: "Expenses", role: "expense" },
        ],
        data: [
          { x: "2026-09-28", income: 0, expense: 1200 },
          { x: "2026-09-29", income: 0, expense: 850 },
          { x: "2026-09-30", income: 25000, expense: 2100 },
          { x: "2026-10-01", income: 0, expense: 1500 },
          { x: "2026-10-02", income: 0, expense: 950 },
          { x: "2026-10-03", income: 0, expense: 1100 },
          { x: "2026-10-04", income: 0, expense: 700 },
        ],
      },
      {
        type: "chart",
        id: "blk_cht_4",
        title: "Top Expenses",
        kind: "bar",
        x_format: "category",
        y_format: "currency",
        series: [{ key: "amount", label: "Expenses", role: "expense" }],
        data: [
          { x: "Very Long Grocery Store Subcategory Name", amount: 4200 },
          { x: "Utilities", amount: 2100 },
          { x: "Dining Out", amount: 1500 },
          { x: "Transport", amount: 600 },
        ],
      },
      {
        type: "notice",
        id: "blk_not_2",
        tone: "info",
        text: "2 income/expense entries have no type and were left out.",
      },
      // Unknown block to verify graceful degradation
      {
        type: "future_propose_entry_card",
        id: "blk_unknown_1",
        title: "This should render nothing",
      },
    ],
  },
};
