/**
 * Pure math module for RiskLens Simulation Lab (CC2).
 * Contains pure projection math, interpolation, formatters, bounds and defaults.
 * No UI or React dependencies.
 */

// ── Role & Styling Map (CC3) ──────────────────────────────────────────────────

export type SimulationRole = "baseline" | "expected" | "best" | "risk" | "buy" | "rent";

export interface LineStyle {
  role: SimulationRole;
  color: { light: string; dark: string };
  dash?: string;
  name: string;
}

export const CHART_STYLES: Record<SimulationRole, { color: { light: string; dark: string }; dash?: string }> = {
  baseline: {
    color: { light: "#6B7280", dark: "#9CA3AF" }, // gray, dashed
    dash: "5 5",
  },
  expected: {
    color: { light: "#2563EB", dark: "#60A5FA" }, // blue, solid
    dash: undefined,
  },
  best: {
    color: { light: "#16A34A", dark: "#4ADE80" }, // green, solid
    dash: undefined,
  },
  risk: {
    color: { light: "#DC2626", dark: "#F87171" }, // red, solid
    dash: undefined,
  },
  buy: {
    color: { light: "#7C3AED", dark: "#A78BFA" }, // purple, solid
    dash: undefined,
  },
  rent: {
    color: { light: "#D97706", dark: "#FBBF24" }, // amber, solid
    dash: undefined,
  },
};

export const LABEL_ALIAS_MAP: Record<string, SimulationRole> = {
  current_path_expected: "baseline",
  current_baseline: "baseline",
  without_program: "baseline",
  expected_case: "expected",
  best_case: "best",
  risk_case: "risk",
  Buy: "buy",
  Rent: "rent",
};

export function resolveRole(label: string): SimulationRole {
  return LABEL_ALIAS_MAP[label] || "baseline";
}

export function getScenarioDisplayName(scenarioType: string, label: string): string {
  const role = resolveRole(label);
  switch (scenarioType) {
    case "increase_savings_rate":
      if (role === "baseline") return "Current Trajectory";
      if (role === "expected") return "Target Rate";
      break;
    case "fitness_plan":
      if (role === "baseline") return "Historical Baseline";
      if (role === "expected") return "Target Plan";
      if (role === "best") return "Best Case";
      if (role === "risk") return "Risk Case";
      break;
    case "reduce_study_hours":
      if (role === "expected") return "Expected Score";
      if (role === "best") return "Best Case";
      if (role === "risk") return "Risk Case";
      break;
    case "buy_vs_rent":
      if (label === "Buy" || role === "buy") return "Buy (Property Equity & Portfolio)";
      if (label === "Rent" || role === "rent") return "Rent (Invested Portfolio)";
      break;
    case "program_outcome":
      if (label === "without_program" || role === "baseline") return "Current Path";
      if (role === "expected") return "Expected Post-Program";
      if (role === "best") return "Best Case (+10%)";
      if (role === "risk") return "Risk Case (-10%)";
      break;
  }
  return label.replace(/_/g, " ");
}

// ── Bounds & Defaults (CC7, CC8) ─────────────────────────────────────────────

export const SIM_BOUNDS = {
  increase_savings_rate: {
    target_rate: { min: 0.01, max: 100 },
    horizon_months: { min: 1, max: 120 },
  },
  fitness_plan: {
    target_weekly_minutes: { min: 1, max: 10080 },
    horizon_days: { min: 7, max: 365 },
    history_days: { min: 14, max: 365 },
  },
  reduce_study_hours: {
    window_days: [7, 14],
    current_daily_hours: { min: 0, max: 8 },
    simulated_daily_hours: { min: 0, max: 8 },
  },
  buy_vs_rent: {
    home_price: { min: 1 },
    down_payment_pct: { min: 0, max: 100 },
    expected_home_appreciation_pct_per_year: { min: -10, max: 30 },
    maintenance_pct_per_year: { min: 0, max: 20 },
    property_tax_pct_per_year: { min: 0, max: 20 },
    selling_costs_pct: { min: 0, max: 30 },
    mortgage_rate_pct: { min: 0, max: 30 },
    loan_term_years: { min: 1, max: 40 },
    closing_costs_pct: { min: 0, max: 20 },
    current_monthly_rent: { min: 1 },
    expected_rent_increase_pct_per_year: { min: 0, max: 30 },
    security_deposit_months: { min: 0, max: 24 },
    expected_investment_return_pct_per_year: { min: 0, max: 40 },
    inflation_pct_per_year: { min: -5, max: 30 },
    portfolio_gains_tax_pct: { min: 0, max: 60 },
    property_gains_tax_pct: { min: 0, max: 60 },
    horizon_years: { min: 1, max: 40 },
  },
  program_outcome: {
    current_annual_salary: { min: 0.01 },
    program_tuition_cost: { min: 0.01 },
    program_duration_years: { min: 0.5, max: 10.0 },
    expected_salary_post_program: { min: 0.01 },
    opportunity_cost_income_during_program: { min: 0 },
  },
} as const;

export const SIM_DEFAULTS = {
  increase_savings_rate: {
    target_rate: 20,
    horizon_months: 60,
    window_start: null as string | null,
    window_end: null as string | null,
  },
  fitness_plan: {
    target_weekly_minutes: 150,
    horizon_days: 90,
    history_days: 90,
  },
  reduce_study_hours: {
    window_days: 14,
    current_daily_hours: 2.0,
    simulated_daily_hours: 3.0,
    subject: "",
    assessment_type: "",
  },
  buy_vs_rent: {
    home_price: 5000000,
    down_payment_pct: 20,
    expected_home_appreciation_pct_per_year: 7,
    maintenance_pct_per_year: 1,
    property_tax_pct_per_year: 1,
    selling_costs_pct: 6,
    mortgage_rate_pct: 8.5,
    loan_term_years: 20,
    closing_costs_pct: 3,
    current_monthly_rent: 25000,
    expected_rent_increase_pct_per_year: 5,
    security_deposit_months: 2,
    expected_investment_return_pct_per_year: 12,
    inflation_pct_per_year: 5,
    output_basis: "nominal" as "nominal" | "real",
    portfolio_gains_tax_pct: 0,
    property_gains_tax_pct: 0,
    horizon_years: 20,
  },
  program_outcome: {
    current_annual_salary: "",
    program_tuition_cost: "",
    program_duration_years: "",
    expected_salary_post_program: "",
    opportunity_cost_income_during_program: "",
  },
};

// ── Pure Projection Math ─────────────────────────────────────────────────────

export interface ProjectionPoint {
  x: number;
  date: string;
  value: number;
}

/**
 * S1: Dynamic cumulative wealth projection.
 * Formula:
 * baseline(N) = baseSavings + currentRate * avgMonthlyIncome * N
 * expected(N) = baseSavings + targetRate * avgMonthlyIncome * N
 */
export function projectSavings(
  baseSavings: number,
  avgMonthlyIncome: number,
  currentRate: number,
  targetRate: number,
  horizonMonths: number,
  startDateStr?: string
): { currentPath: ProjectionPoint[]; expectedPath: ProjectionPoint[] } {
  const currentPath: ProjectionPoint[] = [];
  const expectedPath: ProjectionPoint[] = [];

  const start = startDateStr ? new Date(startDateStr) : new Date();

  for (let n = 0; n <= horizonMonths; n++) {
    const d = new Date(start);
    d.setMonth(d.getMonth() + n);
    const dateStr = d.toISOString().slice(0, 7); // YYYY-MM

    currentPath.push({
      x: n,
      date: dateStr,
      value: baseSavings + currentRate * avgMonthlyIncome * n,
    });
    expectedPath.push({
      x: n,
      date: dateStr,
      value: baseSavings + targetRate * avgMonthlyIncome * n,
    });
  }

  return { currentPath, expectedPath };
}

/**
 * S2: Dynamic fitness plan projection and 80% variability band.
 * z = 1.2816 (80% two-sided normal)
 * T = targetWeeklyMinutes / 7 (daily target)
 * baseline = historicalDailyAvg * D
 * expected = T * D
 * best = T * D + z * sigma * sqrt(D)
 * risk = max(0, T * D - z * sigma * sqrt(D))
 */
export function projectFitness(
  historicalDailyAvg: number,
  dailyStdDev: number,
  targetWeeklyMinutes: number,
  horizonDays: number,
  startDateStr?: string
): {
  baseline: ProjectionPoint[];
  expected: ProjectionPoint[];
  best: ProjectionPoint[];
  risk: ProjectionPoint[];
} {
  const z = 1.2816;
  const targetDailyMinutes = targetWeeklyMinutes / 7;
  const start = startDateStr ? new Date(startDateStr) : new Date();

  const baseline: ProjectionPoint[] = [];
  const expected: ProjectionPoint[] = [];
  const best: ProjectionPoint[] = [];
  const risk: ProjectionPoint[] = [];

  for (let d = 0; d <= horizonDays; d++) {
    const dt = new Date(start);
    dt.setDate(dt.getDate() + d);
    const dateStr = dt.toISOString().slice(0, 10);

    const baseVal = historicalDailyAvg * d;
    const expVal = targetDailyMinutes * d;
    const spread = z * dailyStdDev * Math.sqrt(d);
    const bestVal = expVal + spread;
    const riskVal = Math.max(0, expVal - spread);

    baseline.push({ x: d, date: dateStr, value: Math.round(baseVal * 10) / 10 });
    expected.push({ x: d, date: dateStr, value: Math.round(expVal * 10) / 10 });
    best.push({ x: d, date: dateStr, value: Math.round(bestVal * 10) / 10 });
    risk.push({ x: d, date: dateStr, value: Math.round(riskVal * 10) / 10 });
  }

  return { baseline, expected, best, risk };
}

/**
 * S3: Interpolate monotonic curve grid points (0.0 - 8.0, step 0.1).
 */
export function interpolateCurve(
  points: Array<{ x?: number; value: number }>,
  targetX: number
): number {
  if (!points || points.length === 0) return 0;
  if (points.length === 1) return Math.min(100, Math.max(0, points[0].value));

  // Ensure x exists on points
  const pts = points.map((p, i) => ({ x: p.x ?? i, value: p.value }));

  // Clamping to boundaries
  if (targetX <= pts[0].x) return Math.min(100, Math.max(0, pts[0].value));
  if (targetX >= pts[pts.length - 1].x) return Math.min(100, Math.max(0, pts[pts.length - 1].value));

  // Find enclosing interval
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i];
    const p1 = pts[i + 1];
    if (targetX >= p0.x && targetX <= p1.x) {
      if (p1.x === p0.x) return p0.value;
      const t = (targetX - p0.x) / (p1.x - p0.x);
      const val = p0.value + t * (p1.value - p0.value);
      return Math.min(100, Math.max(0, val));
    }
  }

  return pts[pts.length - 1].value;
}

/**
 * S4: Standard monthly loan EMI calculation.
 */
export function calculateMortgageEMI(
  principal: number,
  annualRatePct: number,
  termYears: number
): number {
  if (principal <= 0 || termYears <= 0) return 0;
  if (annualRatePct <= 0) {
    return principal / (termYears * 12);
  }
  const r = annualRatePct / 100 / 12;
  const n = termYears * 12;
  const emi = (principal * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
  return Math.round(emi * 100) / 100;
}

// ── Compact INR & Axis Formatters (CC4) ───────────────────────────────────────

/**
 * Compact Indian Rupee (INR) formatter with K / L / Cr formatting.
 * Examples:
 * 500 -> ₹500
 * 12,000 -> ₹12K
 * 1,50,000 -> ₹1.5L
 * 50,00,000 -> ₹50L
 * 1,20,00,000 -> ₹1.2Cr
 * Handles negative numbers seamlessly: -₹50K.
 */
export function formatCompactINR(val: number): string {
  if (isNaN(val) || val === 0) return "₹0";

  const isNeg = val < 0;
  const abs = Math.abs(val);

  let formatted = "";
  if (abs >= 10000000) {
    const cr = abs / 10000000;
    formatted = cr >= 100 ? `${Math.round(cr)}Cr` : `${parseFloat(cr.toFixed(2))}Cr`;
  } else if (abs >= 100000) {
    const lakh = abs / 100000;
    formatted = lakh >= 100 ? `${Math.round(lakh)}L` : `${parseFloat(lakh.toFixed(2))}L`;
  } else if (abs >= 1000) {
    const k = abs / 1000;
    formatted = k >= 100 ? `${Math.round(k)}K` : `${parseFloat(k.toFixed(1))}K`;
  } else {
    formatted = Math.round(abs).toString();
  }

  return isNeg ? `-₹${formatted}` : `₹${formatted}`;
}

/**
 * X-axis tick formatter per scenario.
 */
export function formatScenarioXTick(scenarioType: string, x: number): string {
  switch (scenarioType) {
    case "increase_savings_rate":
      return `M${x}`;
    case "fitness_plan":
      return `Day ${x}`;
    case "reduce_study_hours":
      return `${x}h`;
    case "buy_vs_rent":
      return `Yr ${x}`;
    case "program_outcome":
      return `Year ${x}`;
    default:
      return `${x}`;
  }
}
