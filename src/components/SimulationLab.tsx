import { useState, useEffect, useCallback, useRef } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Legend,
  Area,
  AreaChart,
} from "recharts";
import { I } from "./icons";
import { Btn, Chip, Field, Input, toast } from "./ui";
import { useTheme } from "../state/ThemeContext";
import { apiRequest } from "../lib/api";
import { formatCurrency, formatINR } from "../lib/currency";
import type { NavRoute } from "./Sidebar";

/* ══════════════════════════════════════════════════════════════════
   TYPES
   ══════════════════════════════════════════════════════════════════ */

interface SimulationPoint {
  date: string;
  value: number;
}

interface SimulationLine {
  label: string;
  points: SimulationPoint[];
}

interface RecommendationItem {
  title: string;
  impact: "High" | "Medium" | "Low";
  effort: "High" | "Medium" | "Low";
  description: string;
}

interface SimulationResponse {
  id: string;
  scenario_type: string;
  reliability: string;
  data_point_count: number | null;
  message: string | null;
  lines: SimulationLine[];
  generated_at: string;
  correlation_r_squared: number | null;
  derived_values: Record<string, unknown> | null;
  recommendations: RecommendationItem[] | null;
  recommendations_status: "pending" | "ready" | "unavailable";
  recommendation_disclaimer: string | null;
}

type ScenarioType =
  | "increase_savings_rate"
  | "fitness_plan"
  | "reduce_study_hours"
  | "buy_vs_rent"
  | "program_outcome";

interface ScenarioMeta {
  id: ScenarioType;
  title: string;
  icon: string;
  description: string;
  category: "data_driven" | "assumption_based";
}

/* ══════════════════════════════════════════════════════════════════
   SCENARIO METADATA
   ══════════════════════════════════════════════════════════════════ */

const SCENARIOS: ScenarioMeta[] = [
  {
    id: "increase_savings_rate",
    title: "Increase Savings Rate",
    icon: "chart",
    description:
      "Project what your savings could look like at a target rate, based on your actual tracked income and savings history.",
    category: "data_driven",
  },
  {
    id: "fitness_plan",
    title: "Fitness Plan",
    icon: "activity",
    description:
      "Forecast your fitness trajectory toward a target weekly minutes goal, based on your tracked workout data.",
    category: "data_driven",
  },
  {
    id: "reduce_study_hours",
    title: "Reduce Study Hours",
    icon: "brain",
    description:
      "Analyze the correlation between study time and academic performance to find a more efficient schedule.",
    category: "data_driven",
  },
  {
    id: "buy_vs_rent",
    title: "Buy vs Rent",
    icon: "home",
    description:
      "Compare the long-term financial outcome of buying a home vs. continuing to rent, using your real accumulated savings as the starting capital.",
    category: "assumption_based",
  },
  {
    id: "program_outcome",
    title: "Program Outcome",
    icon: "award",
    description:
      "Model the return on investment of an education program or career change, comparing salary trajectories over 10 years.",
    category: "assumption_based",
  },
];

/* ══════════════════════════════════════════════════════════════════
   CHART COLORS
   ══════════════════════════════════════════════════════════════════ */

const CHART_COLORS = {
  current: { light: "#5B4CC4", dark: "#A855F7" },
  expected: { light: "#16A34A", dark: "#34D399" },
  best: { light: "#0284C7", dark: "#38BDF8" },
  risk: { light: "#DC2626", dark: "#FB7185" },
  buy: { light: "#5B4CC4", dark: "#A855F7" },
  rent: { light: "#D97706", dark: "#FBBF24" },
};

/* ══════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ══════════════════════════════════════════════════════════════════ */

export function SimulationLab({ onNavigate }: { onNavigate?: (r: NavRoute) => void }) {
  const { isDark } = useTheme();
  const [selectedScenario, setSelectedScenario] = useState<ScenarioType | null>(null);
  const [result, setResult] = useState<SimulationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const pollRef = useRef<number | null>(null);
  const [goalCreated, setGoalCreated] = useState(false);

  // Param states for data-driven scenarios
  const [targetRate, setTargetRate] = useState("20");
  const [targetWeeklyMinutes, setTargetWeeklyMinutes] = useState("150");
  const [targetWeeklyHours, setTargetWeeklyHours] = useState("8");

  // Param states for Buy vs Rent
  const [bvrParams, setBvrParams] = useState({
    home_price: "5000000",
    mortgage_rate_pct: "8.5",
    loan_term_years: "20",
    current_monthly_rent: "25000",
    expected_rent_increase_pct_per_year: "5",
    expected_home_appreciation_pct_per_year: "7",
    expected_investment_return_pct_per_year: "12",
  });

  // Param states for Program Outcome
  const [poParams, setPoParams] = useState({
    current_annual_salary: "500000",
    program_tuition_cost: "200000",
    program_duration_years: "2",
    expected_salary_post_program: "800000",
    opportunity_cost_income_during_program: "0",
  });

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Start polling for recommendations
  const startPolling = useCallback(
    (simId: string) => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = window.setInterval(async () => {
        try {
          const res = await apiRequest<SimulationResponse>(`/simulations/${simId}`);
          if (res.recommendations_status !== "pending") {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setResult(res);
          }
        } catch {
          // Silently retry — if network fails, polling will catch it next cycle
        }
      }, 3500);
    },
    []
  );

  // ── CLIENT-SIDE VALIDATION ──────────────────────────────────────

  function validateParams(): Record<string, string> | null {
    const errs: Record<string, string> = {};

    if (selectedScenario === "increase_savings_rate") {
      const v = parseFloat(targetRate);
      if (isNaN(v) || v <= 0 || v > 100) errs.target_rate = "Rate must be between 0.01% and 100%.";
    } else if (selectedScenario === "fitness_plan") {
      const v = parseFloat(targetWeeklyMinutes);
      if (isNaN(v) || v <= 0) errs.target_weekly_minutes = "Target must be a positive number.";
    } else if (selectedScenario === "reduce_study_hours") {
      const v = parseFloat(targetWeeklyHours);
      if (isNaN(v) || v <= 0) errs.target_weekly_hours = "Target must be a positive number.";
    } else if (selectedScenario === "buy_vs_rent") {
      const p = bvrParams;
      if (!parseFloat(p.home_price) || parseFloat(p.home_price) <= 0)
        errs.home_price = "Must be a positive number.";
      if (!parseFloat(p.mortgage_rate_pct) || parseFloat(p.mortgage_rate_pct) <= 0)
        errs.mortgage_rate_pct = "Must be a positive number.";
      if (!parseInt(p.loan_term_years) || parseInt(p.loan_term_years) <= 0)
        errs.loan_term_years = "Must be a positive integer.";
      if (!parseFloat(p.current_monthly_rent) || parseFloat(p.current_monthly_rent) <= 0)
        errs.current_monthly_rent = "Must be a positive number.";
      if (!parseFloat(p.expected_rent_increase_pct_per_year) || parseFloat(p.expected_rent_increase_pct_per_year) <= 0)
        errs.expected_rent_increase_pct_per_year = "Must be a positive number.";
      if (!parseFloat(p.expected_home_appreciation_pct_per_year) || parseFloat(p.expected_home_appreciation_pct_per_year) <= 0)
        errs.expected_home_appreciation_pct_per_year = "Must be a positive number.";
      if (!parseFloat(p.expected_investment_return_pct_per_year) || parseFloat(p.expected_investment_return_pct_per_year) <= 0)
        errs.expected_investment_return_pct_per_year = "Must be a positive number.";
    } else if (selectedScenario === "program_outcome") {
      const p = poParams;
      if (!parseFloat(p.current_annual_salary) || parseFloat(p.current_annual_salary) <= 0)
        errs.current_annual_salary = "Must be a positive number.";
      if (!parseFloat(p.program_tuition_cost) || parseFloat(p.program_tuition_cost) <= 0)
        errs.program_tuition_cost = "Must be a positive number.";
      const dur = parseFloat(p.program_duration_years);
      if (isNaN(dur) || dur < 0.5 || dur > 10)
        errs.program_duration_years = "Must be between 0.5 and 10 years.";
      if (!parseFloat(p.expected_salary_post_program) || parseFloat(p.expected_salary_post_program) <= 0)
        errs.expected_salary_post_program = "Must be a positive number.";
      const opp = parseFloat(p.opportunity_cost_income_during_program);
      if (isNaN(opp) || opp < 0)
        errs.opportunity_cost_income_during_program = "Must be zero or positive.";
    }

    return Object.keys(errs).length > 0 ? errs : null;
  }

  // ── RUN SIMULATION ──────────────────────────────────────────────

  async function runSimulation() {
    if (!selectedScenario) return;

    const errs = validateParams();
    if (errs) {
      setFieldErrors(errs);
      return;
    }
    setFieldErrors({});
    setError(null);
    setLoading(true);
    setResult(null);
    setGoalCreated(false);
    if (pollRef.current) clearInterval(pollRef.current);

    let params: Record<string, unknown> = {};

    switch (selectedScenario) {
      case "increase_savings_rate":
        params = { target_rate: parseFloat(targetRate) / 100 };
        break;
      case "fitness_plan":
        params = { target_weekly_minutes: parseFloat(targetWeeklyMinutes) };
        break;
      case "reduce_study_hours":
        params = { target_weekly_hours: parseFloat(targetWeeklyHours) };
        break;
      case "buy_vs_rent":
        params = {
          home_price: parseFloat(bvrParams.home_price),
          mortgage_rate_pct: parseFloat(bvrParams.mortgage_rate_pct),
          loan_term_years: parseInt(bvrParams.loan_term_years),
          current_monthly_rent: parseFloat(bvrParams.current_monthly_rent),
          expected_rent_increase_pct_per_year: parseFloat(bvrParams.expected_rent_increase_pct_per_year),
          expected_home_appreciation_pct_per_year: parseFloat(bvrParams.expected_home_appreciation_pct_per_year),
          expected_investment_return_pct_per_year: parseFloat(bvrParams.expected_investment_return_pct_per_year),
        };
        break;
      case "program_outcome":
        params = {
          current_annual_salary: parseFloat(poParams.current_annual_salary),
          program_tuition_cost: parseFloat(poParams.program_tuition_cost),
          program_duration_years: parseFloat(poParams.program_duration_years),
          expected_salary_post_program: parseFloat(poParams.expected_salary_post_program),
          opportunity_cost_income_during_program: parseFloat(poParams.opportunity_cost_income_during_program),
        };
        break;
    }

    try {
      const res = await apiRequest<SimulationResponse>("/simulations", {
        method: "POST",
        body: JSON.stringify({
          scenario_type: selectedScenario,
          params,
        }),
      });
      setResult(res);

      // Start polling for recommendations if pending
      if (res.recommendations_status === "pending") {
        startPolling(res.id);
      }
    } catch (err: unknown) {
      if (err && typeof err === "object" && "status" in err) {
        const apiErr = err as { status: number; message?: string; detail?: unknown };
        if (apiErr.status === 422 && apiErr.detail && Array.isArray(apiErr.detail)) {
          const fErrs: Record<string, string> = {};
          for (const d of apiErr.detail as Array<{ field?: string; message?: string }>) {
            if (d.field) fErrs[d.field] = d.message || "Invalid value";
          }
          setFieldErrors(fErrs);
        } else {
          setError(apiErr.message || "Something went wrong. Please try again.");
        }
      } else {
        setError("Unable to connect to the server. Please check your connection.");
      }
    } finally {
      setLoading(false);
    }
  }

  // ── TURN INTO GOAL ──────────────────────────────────────────────

  async function createGoalFromResult() {
    if (!result || !result.derived_values) return;

    let title = "";
    let target = 0;
    let current = 0;
    let unit = "";
    let deadlineDate = "";

    if (result.scenario_type === "increase_savings_rate") {
      // Target = projected cumulative amount at target rate at 5-year horizon
      const expectedLine = result.lines.find((l) => l.label === "expected_case");
      const lastPoint = expectedLine?.points?.[expectedLine.points.length - 1];
      target = lastPoint ? lastPoint.value : 0;
      current = 0;
      unit = "INR";
      title = `Save ${formatCurrency(target)} in 5 Years`;
      const d = new Date();
      d.setFullYear(d.getFullYear() + 5);
      deadlineDate = d.toISOString().slice(0, 10);
    } else if (result.scenario_type === "fitness_plan") {
      const dv = result.derived_values;
      target = (dv.target_weekly_minutes as number) || 0;
      current = (dv.current_avg_minutes as number) || 0;
      unit = "minutes";
      title = `Reach ${target} Weekly Fitness Minutes`;
      const d = new Date();
      d.setMonth(d.getMonth() + 3);
      deadlineDate = d.toISOString().slice(0, 10);
    } else {
      return; // No natural goal mapping
    }

    try {
      await apiRequest("/goals", {
        method: "POST",
        body: JSON.stringify({
          title,
          target,
          current,
          unit,
          deadline: deadlineDate,
        }),
      });
      setGoalCreated(true);
      toast(`Goal "${title}" created!`, "ok");
    } catch {
      toast("Failed to create goal. Please try again.", "err");
    }
  }

  // ── RENDER: SCENARIO SELECTOR ───────────────────────────────────

  if (!selectedScenario) {
    return (
      <div className="space-y-5 anim-rise">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl bg-gradient-primary flex items-center justify-center text-white shadow-md">
            <I name="activity" size={20} />
          </div>
          <div>
            <h2 className="font-display font-bold text-[18px] text-ink">Simulation Lab</h2>
            <p className="text-[12.5px] text-ink-soft">Run what-if scenarios on your real data</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {SCENARIOS.map((s, i) => (
            <button
              key={s.id}
              onClick={() => {
                setSelectedScenario(s.id);
                setResult(null);
                setError(null);
                setFieldErrors({});
                setGoalCreated(false);
              }}
              className="stagger group text-left rounded-xl border border-line bg-card p-4 hover:border-primary/40 hover:shadow-md transition-all duration-200 focus-ring"
              style={{ "--i": i } as React.CSSProperties}
            >
              <div className="flex items-start gap-3 mb-2.5">
                <div className="w-9 h-9 rounded-lg bg-primary-soft text-primary flex items-center justify-center shrink-0 group-hover:bg-gradient-primary group-hover:text-white transition-colors">
                  <I name={s.icon} size={18} />
                </div>
                <div className="min-w-0">
                  <h3 className="font-display font-semibold text-[14px] text-ink leading-tight">
                    {s.title}
                  </h3>
                  <Chip
                    tone={s.category === "data_driven" ? "primary" : "warn"}
                    className="mt-1"
                  >
                    {s.category === "data_driven" ? "Your tracked data" : "Hypothetical inputs"}
                  </Chip>
                </div>
              </div>
              <p className="text-[12px] text-ink-soft leading-relaxed">{s.description}</p>
            </button>
          ))}
        </div>
      </div>
    );
  }

  const scenarioMeta = SCENARIOS.find((s) => s.id === selectedScenario)!;

  // ── RENDER: PARAM INPUT + RESULTS ───────────────────────────────

  return (
    <div className="space-y-5 anim-rise">
      {/* Header with back button */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => {
            setSelectedScenario(null);
            setResult(null);
            setError(null);
            setFieldErrors({});
            if (pollRef.current) clearInterval(pollRef.current);
          }}
          className="p-2 -ml-1 rounded-lg text-ink-soft hover:text-ink hover:bg-bg-soft transition-colors focus-ring"
        >
          <I name="arrow-left" size={18} />
        </button>
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-gradient-primary text-white flex items-center justify-center shadow-sm">
            <I name={scenarioMeta.icon} size={18} />
          </div>
          <div>
            <h2 className="font-display font-bold text-[17px] text-ink">{scenarioMeta.title}</h2>
            <p className="text-[11.5px] text-ink-soft">{scenarioMeta.description}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* LEFT: Parameter Input */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-xl border border-line bg-card p-5 shadow-xs">
            <h3 className="font-display font-semibold text-[14px] text-ink mb-4 flex items-center gap-2">
              <I name="settings" size={15} />
              Parameters
            </h3>

            {/* Data-driven: simple single input */}
            {selectedScenario === "increase_savings_rate" && (
              <div className="max-w-xs">
                <Field label="Target Savings Rate (%)" error={fieldErrors.target_rate}>
                  <Input
                    type="number"
                    value={targetRate}
                    onChange={(e) => setTargetRate(e.target.value)}
                    placeholder="e.g. 25"
                    min={0.01}
                    max={100}
                    step={0.1}
                    invalid={!!fieldErrors.target_rate}
                  />
                </Field>
              </div>
            )}

            {selectedScenario === "fitness_plan" && (
              <div className="max-w-xs">
                <Field label="Target Weekly Minutes" error={fieldErrors.target_weekly_minutes}>
                  <Input
                    type="number"
                    value={targetWeeklyMinutes}
                    onChange={(e) => setTargetWeeklyMinutes(e.target.value)}
                    placeholder="e.g. 200"
                    min={1}
                    invalid={!!fieldErrors.target_weekly_minutes}
                  />
                </Field>
              </div>
            )}

            {selectedScenario === "reduce_study_hours" && (
              <div className="max-w-xs">
                <Field label="Target Weekly Study Hours" error={fieldErrors.target_weekly_hours}>
                  <Input
                    type="number"
                    value={targetWeeklyHours}
                    onChange={(e) => setTargetWeeklyHours(e.target.value)}
                    placeholder="e.g. 8"
                    min={1}
                    step={0.5}
                    invalid={!!fieldErrors.target_weekly_hours}
                  />
                </Field>
              </div>
            )}

            {/* Buy vs Rent: 7 fields */}
            {selectedScenario === "buy_vs_rent" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  { key: "home_price", label: "Home Price (₹)", placeholder: "5000000" },
                  { key: "mortgage_rate_pct", label: "Mortgage Rate (%)", placeholder: "8.5" },
                  { key: "loan_term_years", label: "Loan Term (years)", placeholder: "20" },
                  { key: "current_monthly_rent", label: "Current Monthly Rent (₹)", placeholder: "25000" },
                  { key: "expected_rent_increase_pct_per_year", label: "Expected Rent Increase (%/yr)", placeholder: "5" },
                  { key: "expected_home_appreciation_pct_per_year", label: "Home Appreciation (%/yr)", placeholder: "7" },
                  { key: "expected_investment_return_pct_per_year", label: "Investment Return (%/yr)", placeholder: "12" },
                ].map((f) => (
                  <Field key={f.key} label={f.label} error={fieldErrors[f.key]}>
                    <Input
                      type="number"
                      value={bvrParams[f.key as keyof typeof bvrParams]}
                      onChange={(e) =>
                        setBvrParams((p) => ({ ...p, [f.key]: e.target.value }))
                      }
                      placeholder={f.placeholder}
                      invalid={!!fieldErrors[f.key]}
                    />
                  </Field>
                ))}
              </div>
            )}

            {/* Program Outcome: 5 fields */}
            {selectedScenario === "program_outcome" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  { key: "current_annual_salary", label: "Current Annual Salary (₹)", placeholder: "500000" },
                  { key: "program_tuition_cost", label: "Program Tuition Cost (₹)", placeholder: "200000" },
                  { key: "program_duration_years", label: "Program Duration (years)", placeholder: "2", hint: "0.5–10" },
                  { key: "expected_salary_post_program", label: "Expected Salary Post-Program (₹)", placeholder: "800000" },
                  { key: "opportunity_cost_income_during_program", label: "Income Forgone During Program (₹/yr)", placeholder: "0" },
                ].map((f) => (
                  <Field key={f.key} label={f.label} error={fieldErrors[f.key]} hint={f.hint}>
                    <Input
                      type="number"
                      value={poParams[f.key as keyof typeof poParams]}
                      onChange={(e) =>
                        setPoParams((p) => ({ ...p, [f.key]: e.target.value }))
                      }
                      placeholder={f.placeholder}
                      step={f.key === "program_duration_years" ? 0.5 : 1}
                      invalid={!!fieldErrors[f.key]}
                    />
                  </Field>
                ))}
              </div>
            )}

            <div className="mt-4 flex items-center gap-3">
              <Btn onClick={runSimulation} loading={loading}>
                <I name="activity" size={15} />
                Run Simulation
              </Btn>
              {error && (
                <p className="text-[12.5px] text-danger font-medium flex items-center gap-1">
                  <I name="alert" size={13} />
                  {error}
                </p>
              )}
            </div>
          </div>

          {/* RESULTS: Chart + Reliability */}
          {result && (
            <div className="rounded-xl border border-line bg-card p-5 shadow-xs anim-rise">
              {/* Reliability Badge + Provenance */}
              <div className="flex flex-wrap items-center gap-2 mb-4">
                <ReliabilityBadge result={result} />
                <ProvenanceChip result={result} />
              </div>

              {/* Reduce Study Hours: R² + Disclaimer */}
              {result.scenario_type === "reduce_study_hours" && result.correlation_r_squared != null && (
                <div className="mb-4 space-y-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Chip tone="primary">
                      R² = {result.correlation_r_squared.toFixed(3)}
                    </Chip>
                    {result.correlation_r_squared < 0.3 && (
                      <Chip tone="warn">
                        <I name="alert" size={11} />
                        Weak Correlation
                      </Chip>
                    )}
                  </div>
                  <p className="text-[11px] text-ink-faint leading-relaxed italic border-l-2 border-warn/40 pl-3">
                    Based on the correlation observed in your own data, not a guaranteed outcome.
                    Study time and grades may be influenced by many factors not captured here.
                  </p>
                </div>
              )}

              {/* Derived values summary */}
              {result.derived_values && (
                <DerivedValuesSummary result={result} />
              )}

              {/* Chart */}
              {result.lines.length > 0 ? (
                <SimulationChart result={result} isDark={isDark} />
              ) : (
                <div className="h-[200px] flex flex-col items-center justify-center rounded-lg bg-bg-soft/60 border border-dashed border-line text-center p-4">
                  <div className="w-8 h-8 rounded-full bg-warn-soft text-warn flex items-center justify-center mx-auto mb-2">
                    <I name="info" size={16} />
                  </div>
                  <p className="text-[13px] font-semibold text-ink mb-1">Insufficient Data</p>
                  <p className="text-[11.5px] text-ink-soft max-w-[300px]">
                    {result.message || "Not enough tracked data to generate a projection."}
                  </p>
                </div>
              )}

              {/* Turn Into Goal */}
              {(result.scenario_type === "increase_savings_rate" ||
                result.scenario_type === "fitness_plan") &&
                result.lines.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-line">
                    {goalCreated ? (
                      <div className="flex items-center gap-2 text-ok text-[13px] font-medium">
                        <I name="check" size={15} />
                        <span>Goal created!</span>
                        {onNavigate && (
                          <button
                            onClick={() => onNavigate({ view: "category", id: "goals" })}
                            className="text-primary hover:underline ml-1"
                          >
                            View Goals →
                          </button>
                        )}
                      </div>
                    ) : (
                      <Btn variant="subtle" size="sm" onClick={createGoalFromResult}>
                        <I name="flag" size={14} />
                        Turn This Into a Goal
                      </Btn>
                    )}
                  </div>
                )}
            </div>
          )}
        </div>

        {/* RIGHT: Recommendations Sidebar */}
        <div className="lg:col-span-1">
          {result && <RecommendationsSidebar result={result} />}
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   SUB-COMPONENTS
   ══════════════════════════════════════════════════════════════════ */

function ReliabilityBadge({ result }: { result: SimulationResponse }) {
  const r = result.reliability;

  if (r === "assumption_based" && result.scenario_type !== "buy_vs_rent") {
    return (
      <Chip tone="warn">
        <I name="info" size={11} />
        Your hypothetical inputs
      </Chip>
    );
  }

  if (r === "reliable") {
    return (
      <Chip tone="ok">
        <I name="check" size={11} />
        Reliable ({result.data_point_count}+ pts)
      </Chip>
    );
  }

  if (r === "low_confidence") {
    return (
      <Chip tone="warn">
        <I name="alert" size={11} />
        Low Confidence ({result.data_point_count} pts)
      </Chip>
    );
  }

  if (r === "insufficient") {
    return (
      <Chip tone="danger">
        <I name="alert" size={11} />
        Insufficient Data
      </Chip>
    );
  }

  return null;
}

function ProvenanceChip({ result }: { result: SimulationResponse }) {
  // Buy vs Rent: special mixed-provenance chip
  if (result.scenario_type === "buy_vs_rent") {
    const dv = result.derived_values;
    const startingCapital = dv?.starting_capital_from_savings as number | undefined;
    return (
      <Chip tone="custom" className="bg-primary-soft/50 text-ink-soft border border-primary/15 text-[11px]">
        Starting amount: your tracked savings
        {startingCapital != null && ` (${formatCurrency(startingCapital)})`}
        {" · "}Growth assumptions: hypothetical inputs
      </Chip>
    );
  }

  // Savings Rate: show current/target rate
  if (
    result.scenario_type === "increase_savings_rate" &&
    result.derived_values
  ) {
    const dv = result.derived_values;
    const currentRate = dv.current_rate as number | undefined;
    const targetRateVal = dv.target_rate as number | undefined;
    return (
      <Chip tone="primary">
        {currentRate != null && `Current: ${(currentRate * 100).toFixed(1)}%`}
        {currentRate != null && targetRateVal != null && " → "}
        {targetRateVal != null && `Target: ${(targetRateVal * 100).toFixed(1)}%`}
      </Chip>
    );
  }

  return null;
}

function DerivedValuesSummary({ result }: { result: SimulationResponse }) {
  const dv = result.derived_values!;

  if (result.scenario_type === "increase_savings_rate") {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
        {[
          { label: "Current Rate", value: `${((dv.current_rate as number) * 100).toFixed(1)}%` },
          { label: "Target Rate", value: `${((dv.target_rate as number) * 100).toFixed(1)}%` },
          { label: "Income (window)", value: formatCurrency(dv.total_income_in_window as number) },
          { label: "Savings (window)", value: formatCurrency(dv.total_savings_in_window as number) },
        ].map((m) => (
          <div key={m.label} className="rounded-lg bg-bg-soft p-2.5">
            <p className="text-[10px] text-ink-faint uppercase tracking-wider">{m.label}</p>
            <p className="text-[14px] font-bold text-ink mt-0.5">{m.value}</p>
          </div>
        ))}
      </div>
    );
  }

  if (result.scenario_type === "fitness_plan") {
    return (
      <div className="grid grid-cols-2 gap-2 mb-4">
        {[
          { label: "Current Avg", value: `${((dv.current_avg_minutes as number) || 0).toFixed(0)} min/wk` },
          { label: "Target", value: `${(dv.target_weekly_minutes as number) || 0} min/wk` },
        ].map((m) => (
          <div key={m.label} className="rounded-lg bg-bg-soft p-2.5">
            <p className="text-[10px] text-ink-faint uppercase tracking-wider">{m.label}</p>
            <p className="text-[14px] font-bold text-ink mt-0.5">{m.value}</p>
          </div>
        ))}
      </div>
    );
  }

  return null;
}

/* ── CHART ──────────────────────────────────────────────────────── */

function SimulationChart({
  result,
  isDark,
}: {
  result: SimulationResponse;
  isDark: boolean;
}) {
  // Build unified data array for recharts
  const dataMap = new Map<string, Record<string, number>>();
  for (const line of result.lines) {
    for (const pt of line.points) {
      if (!dataMap.has(pt.date)) dataMap.set(pt.date, {});
      dataMap.get(pt.date)![line.label] = pt.value;
    }
  }
  const data = Array.from(dataMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, vals]) => ({ date, ...vals }));

  const lineLabels = result.lines.map((l) => l.label);
  const isCurrency =
    result.scenario_type === "increase_savings_rate" ||
    result.scenario_type === "buy_vs_rent" ||
    result.scenario_type === "program_outcome";

  // Color + style mapping
  function getLineProps(label: string) {
    const mode = isDark ? "dark" : "light";
    switch (label) {
      case "current_path_expected":
        return { color: CHART_COLORS.current[mode], dash: undefined, name: "Current Trajectory" };
      case "expected_case":
        return { color: CHART_COLORS.expected[mode], dash: "6 3", name: "At Target Rate" };
      case "best_case":
        return { color: CHART_COLORS.best[mode], dash: "3 3", name: "Best Case" };
      case "risk_case":
        return { color: CHART_COLORS.risk[mode], dash: "3 3", name: "Risk Case" };
      case "buy_home_equity":
        return { color: CHART_COLORS.buy[mode], dash: undefined, name: "Buy — Home Equity" };
      case "rent_net_position":
        return { color: CHART_COLORS.rent[mode], dash: undefined, name: "Rent — Net Position" };
      case "without_program":
        return { color: CHART_COLORS.current[mode], dash: undefined, name: "Without Program" };
      default:
        return { color: CHART_COLORS.current[mode], dash: undefined, name: label.replace(/_/g, " ") };
    }
  }

  // Check if this is a 4-line confidence-band scenario
  const hasBand =
    (result.scenario_type === "fitness_plan" ||
      result.scenario_type === "reduce_study_hours" ||
      result.scenario_type === "program_outcome") &&
    lineLabels.includes("best_case") &&
    lineLabels.includes("risk_case");

  return (
    <div className="h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        {hasBand ? (
          <AreaChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
            <defs>
              <linearGradient id="simBand" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={isDark ? "#38BDF8" : "#3B82F6"} stopOpacity={isDark ? 0.35 : 0.18} />
                <stop offset="50%" stopColor={isDark ? "#818CF8" : "#6366F1"} stopOpacity={isDark ? 0.22 : 0.10} />
                <stop offset="100%" stopColor={isDark ? "#A855F7" : "#8B5CF6"} stopOpacity={isDark ? 0.10 : 0.04} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: string) => v.slice(5)}
              tick={{ fontSize: 10.5, fill: isDark ? "#CBD5E1" : "#4B5563", fontWeight: 500 }}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10.5, fill: isDark ? "#CBD5E1" : "#4B5563", fontWeight: 500 }}
              tickFormatter={(v: number) => (isCurrency ? `₹${(v / 1000).toFixed(0)}K` : v.toFixed(0))}
            />
            <Tooltip
              formatter={(val: number | string, name: string) => [
                isCurrency ? formatCurrency(Number(val)) : Number(val).toFixed(1),
                name,
              ]}
              labelFormatter={(label) => `Date: ${label}`}
              contentStyle={{
                backgroundColor: isDark ? "#1E2230" : "#FFFFFF",
                borderColor: isDark ? "#333A4E" : "#E5E7EB",
                borderRadius: "8px",
                boxShadow: isDark ? "0 4px 12px rgba(0,0,0,0.5)" : "0 4px 12px rgba(0,0,0,0.08)",
                color: isDark ? "#F8FAFC" : "#1F2937",
                fontSize: "11.5px",
              }}
              itemStyle={{
                color: isDark ? "#F8FAFC" : "#1F2937",
              }}
              labelStyle={{
                color: isDark ? "#94A3B8" : "#64748B",
                fontWeight: 600,
                marginBottom: "4px",
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }}
              formatter={(value: string) => (
                <span style={{ color: isDark ? "#E2E8F0" : "#374151", fontWeight: 500 }}>
                  {value}
                </span>
              )}
              iconType="line"
            />
            {/* Confidence band as area between best_case and risk_case */}
            {lineLabels.includes("best_case") && (
              <Area
                type="monotone"
                dataKey="best_case"
                stroke={isDark ? "rgba(56, 189, 248, 0.45)" : "rgba(59, 130, 246, 0.25)"}
                strokeWidth={1}
                strokeDasharray="4 4"
                fill="url(#simBand)"
                fillOpacity={1}
                name="Confidence Band"
                legendType="rect"
              />
            )}
            {lineLabels.map((label) => {
              const props = getLineProps(label);
              const isPrimary =
                label === "current_path_expected" ||
                label === "without_program" ||
                label === "buy_home_equity";
              return (
                <Line
                  key={label}
                  type="monotone"
                  dataKey={label}
                  stroke={props.color}
                  strokeWidth={isPrimary ? 2.5 : 2}
                  strokeDasharray={props.dash}
                  dot={false}
                  name={props.name}
                />
              );
            })}
          </AreaChart>
        ) : (
          <LineChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: string) => v.slice(5)}
              tick={{ fontSize: 10.5, fill: isDark ? "#CBD5E1" : "#4B5563", fontWeight: 500 }}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10.5, fill: isDark ? "#CBD5E1" : "#4B5563", fontWeight: 500 }}
              tickFormatter={(v: number) => (isCurrency ? `₹${(v / 1000).toFixed(0)}K` : v.toFixed(0))}
            />
            <Tooltip
              formatter={(val: number | string, name: string) => [
                isCurrency ? formatCurrency(Number(val)) : Number(val).toFixed(1),
                name,
              ]}
              labelFormatter={(label) => `Date: ${label}`}
              contentStyle={{
                backgroundColor: isDark ? "#1E2230" : "#FFFFFF",
                borderColor: isDark ? "#333A4E" : "#E5E7EB",
                borderRadius: "8px",
                boxShadow: isDark ? "0 4px 12px rgba(0,0,0,0.5)" : "0 4px 12px rgba(0,0,0,0.08)",
                color: isDark ? "#F8FAFC" : "#1F2937",
                fontSize: "11.5px",
              }}
              itemStyle={{
                color: isDark ? "#F8FAFC" : "#1F2937",
              }}
              labelStyle={{
                color: isDark ? "#94A3B8" : "#64748B",
                fontWeight: 600,
                marginBottom: "4px",
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }}
              formatter={(value: string) => (
                <span style={{ color: isDark ? "#E2E8F0" : "#374151", fontWeight: 500 }}>
                  {value}
                </span>
              )}
              iconType="line"
            />
            {lineLabels.map((label) => {
              const props = getLineProps(label);
              const isPrimary =
                label === "current_path_expected" ||
                label === "without_program" ||
                label === "buy_home_equity";
              return (
                <Line
                  key={label}
                  type="monotone"
                  dataKey={label}
                  stroke={props.color}
                  strokeWidth={isPrimary ? 2.5 : 2}
                  strokeDasharray={props.dash}
                  dot={false}
                  name={props.name}
                />
              );
            })}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

/* ── RECOMMENDATIONS SIDEBAR ──────────────────────────────────── */

function RecommendationsSidebar({ result }: { result: SimulationResponse }) {
  const status = result.recommendations_status;

  return (
    <div className="rounded-xl border border-line bg-card p-4 shadow-xs sticky top-[80px]">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-7 h-7 rounded-lg bg-gradient-primary text-white flex items-center justify-center">
          <I name="brain" size={14} />
        </div>
        <h3 className="font-display font-semibold text-[14px] text-ink">AI Recommendations</h3>
        <Chip tone="primary" className="text-[9px] ml-auto">
          AI Powered
        </Chip>
      </div>

      {status === "pending" && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-lg border border-line bg-bg-soft/50 p-3 animate-pulse">
              <div className="h-3 w-2/3 skeleton rounded mb-2" />
              <div className="h-2 w-full skeleton rounded mb-1" />
              <div className="h-2 w-4/5 skeleton rounded" />
            </div>
          ))}
          <p className="text-[11px] text-ink-faint text-center">Generating recommendations…</p>
        </div>
      )}

      {status === "ready" && result.recommendations && (
        <div className="space-y-2.5">
          {result.recommendations.map((rec, i) => (
            <div
              key={i}
              className="stagger rounded-lg border border-line bg-bg-soft/50 p-3 hover:border-primary/20 transition-colors"
              style={{ "--i": i } as React.CSSProperties}
            >
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <p className="text-[12.5px] font-semibold text-ink leading-tight flex-1">
                  {rec.title}
                </p>
                <Chip tone="primary" className="text-[8.5px] shrink-0">
                  AI Powered
                </Chip>
              </div>
              <p className="text-[11.5px] text-ink-soft leading-relaxed mb-2">
                {rec.description}
              </p>
              <div className="flex items-center gap-1.5">
                <ImpactBadge level={rec.impact} label="Impact" />
                <ImpactBadge level={rec.effort} label="Effort" />
              </div>
            </div>
          ))}

          {/* Savings Rate Disclaimer */}
          {result.recommendation_disclaimer && (
            <p className="text-[10.5px] text-ink-faint italic border-t border-line pt-2 mt-2">
              ⓘ {result.recommendation_disclaimer}
            </p>
          )}
        </div>
      )}

      {status === "unavailable" && (
        <div className="rounded-lg bg-bg-soft/50 border border-line p-4 text-center">
          <I name="info" size={18} className="text-ink-faint mx-auto mb-2" />
          <p className="text-[12px] text-ink-soft leading-relaxed">
            Recommendations couldn't be generated right now — your projection above is still accurate.
          </p>
        </div>
      )}
    </div>
  );
}

function ImpactBadge({ level, label }: { level: "High" | "Medium" | "Low"; label: string }) {
  const tones: Record<string, "ok" | "warn" | "neutral"> = {
    High: "ok",
    Medium: "warn",
    Low: "neutral",
  };
  return (
    <Chip tone={tones[level] || "neutral"} className="text-[9px]">
      {label}: {level}
    </Chip>
  );
}

/* ── DASHBOARD TEASER CARD ─────────────────────────────────────── */

export function SimulationTeaserCard({
  onNavigate,
}: {
  onNavigate: (r: NavRoute) => void;
}) {
  return (
    <button
      onClick={() => onNavigate({ view: "simulation" as unknown as "dashboard" })}
      className="w-full group text-left rounded-xl border border-primary/20 bg-gradient-primary-soft p-4 hover:border-primary/40 hover:shadow-md transition-all duration-200 focus-ring"
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-primary text-white flex items-center justify-center shadow-sm shrink-0 group-hover:scale-105 transition-transform">
          <I name="activity" size={20} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-display font-semibold text-[14px] text-ink mb-0.5">
            Simulation Lab
          </h3>
          <p className="text-[12px] text-ink-soft leading-relaxed">
            What if you saved 25% instead of your current rate? Explore 5 what-if scenarios on your real data.
          </p>
          <span className="inline-flex items-center gap-1 text-[11.5px] font-semibold text-primary mt-2 group-hover:gap-1.5 transition-all">
            Explore Simulation Lab <I name="arrow-right" size={13} />
          </span>
        </div>
      </div>
    </button>
  );
}
