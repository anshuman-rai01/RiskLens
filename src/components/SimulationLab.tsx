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
  ReferenceDot,
  ReferenceLine,
  ReferenceArea,
} from "recharts";
import { I } from "./icons";
import { Btn, Chip, Field, Input, Select, toast } from "./ui";
import { useTheme } from "../state/ThemeContext";
import { apiRequest, ApiError, extractFieldErrors } from "../lib/api";
import { formatCurrency, formatINR } from "../lib/currency";
import {
  formatCompactINR,
  formatScenarioXTick,
  CHART_STYLES,
  resolveRole,
  getScenarioDisplayName,
  SIM_BOUNDS,
  SIM_DEFAULTS,
  projectSavings,
  projectFitness,
  calculateMortgageEMI,
  interpolateCurve,
} from "../lib/simulationMath";
import type { NavRoute } from "./Sidebar";

/* ══════════════════════════════════════════════════════════════════
   TYPES
   ══════════════════════════════════════════════════════════════════ */

interface SimulationPoint {
  date: string;
  value: number;
  x?: number;
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
    title: "Study Hours What-If",
    icon: "brain",
    description:
      "Analyze what happens to your academic scores under different daily study routines based on your tracked historical study and exam results.",
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
  const pollTimeoutRef = useRef<number | null>(null);
  const pollAbortRef = useRef<AbortController | null>(null);
  const currentSimIdRef = useRef<string | null>(null);
  const [goalCreated, setGoalCreated] = useState(false);

  // Param states for data-driven scenarios
  const [targetRate, setTargetRate] = useState("20");
  const [s1HorizonMonths, setS1HorizonMonths] = useState(60);
  const [s1WindowStart, setS1WindowStart] = useState("");
  const [s1WindowEnd, setS1WindowEnd] = useState("");
  const [targetWeeklyMinutes, setTargetWeeklyMinutes] = useState("150");
  const [s2HorizonDays, setS2HorizonDays] = useState(90);
  const [s2HistoryDays, setS2HistoryDays] = useState<number | null>(90);
  // Param states for S3 Study Hours What-If
  const [s3WindowDays, setS3WindowDays] = useState<number>(14);
  const [s3Subject, setS3Subject] = useState<string>("");
  const [s3AssessmentType, setS3AssessmentType] = useState<string>("");
  const [s3CurrentDailyHours, setS3CurrentDailyHours] = useState<number>(2.0);
  const [s3SimulatedDailyHours, setS3SimulatedDailyHours] = useState<number>(3.0);
  const [isUpdating, setIsUpdating] = useState(false);

  const debouncedPostTimeoutRef = useRef<number | null>(null);
  const debouncedPostAbortRef = useRef<AbortController | null>(null);

  // Param states for Buy vs Rent (CC1: editable illustrative assumptions)
  const [bvrParams, setBvrParams] = useState({
    home_price: "5000000",
    down_payment_pct: "20",
    expected_home_appreciation_pct_per_year: "7",
    maintenance_pct_per_year: "1",
    property_tax_pct_per_year: "1",
    selling_costs_pct: "6",
    mortgage_rate_pct: "8.5",
    loan_term_years: "20",
    closing_costs_pct: "3",
    current_monthly_rent: "25000",
    expected_rent_increase_pct_per_year: "5",
    security_deposit_months: "2",
    expected_investment_return_pct_per_year: "12",
    inflation_pct_per_year: "5",
    output_basis: "nominal",
    portfolio_gains_tax_pct: "0",
    property_gains_tax_pct: "0",
    horizon_years: "20",
  });

  // Param states for Program Outcome (empty initial values, not prefilled from tracked data)
  const [poParams, setPoParams] = useState({
    current_annual_salary: "",
    program_tuition_cost: "",
    program_duration_years: "",
    expected_salary_post_program: "",
    opportunity_cost_income_during_program: "",
  });

  // Stop polling and optionally mark recommendations as unavailable (CC6)
  const stopPolling = useCallback((setUnavailable = false) => {
    if (pollTimeoutRef.current != null) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    if (pollAbortRef.current) {
      pollAbortRef.current.abort();
      pollAbortRef.current = null;
    }
    if (setUnavailable) {
      setResult((prev) => {
        if (!prev || prev.recommendations_status === "ready") return prev;
        return { ...prev, recommendations_status: "unavailable" };
      });
    }
  }, []);

  // Hardened recommendation polling (CC6, D6)
  const startPolling = useCallback(
    (simId: string) => {
      stopPolling(false);
      currentSimIdRef.current = simId;
      const abortCtrl = new AbortController();
      pollAbortRef.current = abortCtrl;

      const startTime = Date.now();
      let consecutiveErrors = 0;

      const schedulePoll = (delayMs = 3500) => {
        if (abortCtrl.signal.aborted) return;
        pollTimeoutRef.current = window.setTimeout(async () => {
          if (abortCtrl.signal.aborted) return;

          // 60 s cap check
          if (Date.now() - startTime >= 60000) {
            stopPolling(true);
            return;
          }

          try {
            const res = await apiRequest<SimulationResponse>(`/simulations/${simId}`, {
              signal: abortCtrl.signal,
            });

            if (abortCtrl.signal.aborted || currentSimIdRef.current !== simId || res.id !== simId) {
              return;
            }

            consecutiveErrors = 0;
            if (res.recommendations_status === "ready") {
              setResult((prev) => {
                if (!prev || prev.id !== simId) return prev;
                return {
                  ...prev,
                  recommendations: res.recommendations,
                  recommendations_status: "ready",
                  recommendation_disclaimer: res.recommendation_disclaimer,
                };
              });
              stopPolling(false);
              return;
            } else if (res.recommendations_status === "unavailable" || res.recommendations_status !== "pending") {
              stopPolling(true);
              return;
            }

            // Still pending -> schedule next cycle
            schedulePoll(3500);
          } catch (err: unknown) {
            if (abortCtrl.signal.aborted) return;

            // 404 stops immediately
            if (
              err &&
              typeof err === "object" &&
              "status" in err &&
              (err as { status: number }).status === 404
            ) {
              stopPolling(true);
              return;
            }

            consecutiveErrors++;
            if (consecutiveErrors >= 3) {
              stopPolling(true);
              return;
            }

            schedulePoll(3500);
          }
        }, delayMs);
      };

      schedulePoll(3500);
    },
    [stopPolling]
  );

  // Cleanup polling and debounce on unmount
  useEffect(() => {
    return () => {
      stopPolling(false);
      if (debouncedPostTimeoutRef.current != null) {
        clearTimeout(debouncedPostTimeoutRef.current);
      }
      if (debouncedPostAbortRef.current) {
        debouncedPostAbortRef.current.abort();
      }
    };
  }, [stopPolling]);

  // CC1: Debounced (600ms trailing) POST for parameter changes that re-analyze data or after controls settle
  const triggerDebouncedPost = useCallback(
    (scenarioType: ScenarioType, params: Record<string, unknown>) => {
      if (debouncedPostTimeoutRef.current != null) {
        clearTimeout(debouncedPostTimeoutRef.current);
        debouncedPostTimeoutRef.current = null;
      }
      if (debouncedPostAbortRef.current) {
        debouncedPostAbortRef.current.abort();
        debouncedPostAbortRef.current = null;
      }

      const abortCtrl = new AbortController();
      debouncedPostAbortRef.current = abortCtrl;
      setIsUpdating(true);

      debouncedPostTimeoutRef.current = window.setTimeout(async () => {
        try {
          const res = await apiRequest<SimulationResponse>("/simulations", {
            method: "POST",
            body: JSON.stringify({
              scenario_type: scenarioType,
              params,
            }),
            signal: abortCtrl.signal,
          });

          if (!abortCtrl.signal.aborted) {
            setResult(res);
            setIsUpdating(false);
            if (res.scenario_type === "increase_savings_rate" && res.derived_values) {
              if (res.derived_values.window_start) {
                setS1WindowStart(String(res.derived_values.window_start));
              }
              if (res.derived_values.window_end) {
                setS1WindowEnd(String(res.derived_values.window_end));
              }
              if (res.derived_values.horizon_months) {
                setS1HorizonMonths(Number(res.derived_values.horizon_months));
              }
            } else if (res.scenario_type === "fitness_plan" && res.derived_values) {
              if (res.derived_values.horizon_days) {
                setS2HorizonDays(Number(res.derived_values.horizon_days));
              }
            } else if (res.scenario_type === "reduce_study_hours" && res.derived_values) {
              if (res.derived_values.window_days) {
                setS3WindowDays(Number(res.derived_values.window_days));
              }
            }
            if (res.recommendations_status === "pending") {
              startPolling(res.id);
            }
          }
        } catch (err: unknown) {
          if (abortCtrl.signal.aborted) return;
          setIsUpdating(false);
          if (err instanceof ApiError && err.status === 422 && err.detail) {
            const fErrs = extractFieldErrors(err.detail);
            if (Object.keys(fErrs).length > 0) {
              setFieldErrors(fErrs);
              return;
            }
          }
        }
      }, 600);
    },
    [startPolling]
  );

  // CC1: S1 live controls
  function handleS1TargetRateChange(val: string) {
    setTargetRate(val);
    const rateNum = parseFloat(val);
    if (isNaN(rateNum) || rateNum <= 0 || rateNum > 100) return;

    // Instant client-side formula recompute (zero network calls)
    if (result && result.derived_values) {
      const baseSavings = Number(result.derived_values.base_savings ?? 0);
      const avgIncome = Number(result.derived_values.avg_monthly_income ?? 0);
      const curRate = Number(result.derived_values.current_rate ?? 0);

      const { currentPath, expectedPath } = projectSavings(
        baseSavings,
        avgIncome,
        curRate,
        rateNum / 100,
        s1HorizonMonths,
        result.derived_values.window_start as string | undefined
      );

      setResult((prev) =>
        prev
          ? {
              ...prev,
              lines: [
                { label: "current_path_expected", points: currentPath },
                { label: "expected_case", points: expectedPath },
              ],
              derived_values: {
                ...prev.derived_values,
                target_rate: rateNum / 100,
              },
            }
          : null
      );
    }

    // Debounced POST (600ms) carries full params for recommendations
    triggerDebouncedPost("increase_savings_rate", {
      target_rate: rateNum / 100,
      horizon_months: s1HorizonMonths,
      ...(s1WindowStart ? { window_start: s1WindowStart } : {}),
      ...(s1WindowEnd ? { window_end: s1WindowEnd } : {}),
    });
  }

  function handleS1HorizonChange(months: number) {
    setS1HorizonMonths(months);
    if (months < 1 || months > 120) return;

    const rateNum = parseFloat(targetRate);
    const targetFrac = !isNaN(rateNum) && rateNum > 0 && rateNum <= 100 ? rateNum / 100 : 0.2;

    // Instant client-side formula recompute (zero network calls)
    if (result && result.derived_values) {
      const baseSavings = Number(result.derived_values.base_savings ?? 0);
      const avgIncome = Number(result.derived_values.avg_monthly_income ?? 0);
      const curRate = Number(result.derived_values.current_rate ?? 0);

      const { currentPath, expectedPath } = projectSavings(
        baseSavings,
        avgIncome,
        curRate,
        targetFrac,
        months,
        result.derived_values.window_start as string | undefined
      );

      setResult((prev) =>
        prev
          ? {
              ...prev,
              lines: [
                { label: "current_path_expected", points: currentPath },
                { label: "expected_case", points: expectedPath },
              ],
              derived_values: {
                ...prev.derived_values,
                horizon_months: months,
              },
            }
          : null
      );
    }

    // Debounced POST (600ms) carries full params for recommendations
    triggerDebouncedPost("increase_savings_rate", {
      target_rate: targetFrac,
      horizon_months: months,
      ...(s1WindowStart ? { window_start: s1WindowStart } : {}),
      ...(s1WindowEnd ? { window_end: s1WindowEnd } : {}),
    });
  }

  function handleS1WindowChange(startVal: string, endVal: string) {
    setS1WindowStart(startVal);
    setS1WindowEnd(endVal);

    if (startVal && endVal && startVal >= endVal) {
      setFieldErrors((prev) => ({ ...prev, window_start: "Start date must be before end date." }));
      return;
    }
    setFieldErrors((prev) => {
      const next = { ...prev };
      delete next.window_start;
      delete next.window_end;
      return next;
    });

    const rateNum = parseFloat(targetRate);
    const targetFrac = !isNaN(rateNum) && rateNum > 0 && rateNum <= 100 ? rateNum / 100 : 0.2;

    // Data window changed: triggers debounced POST to re-analyze window
    triggerDebouncedPost("increase_savings_rate", {
      target_rate: targetFrac,
      horizon_months: s1HorizonMonths,
      ...(startVal ? { window_start: startVal } : {}),
      ...(endVal ? { window_end: endVal } : {}),
    });
  }

  // CC1: S2 live controls
  function handleS2TargetChange(val: string) {
    setTargetWeeklyMinutes(val);
    const num = parseFloat(val);
    if (isNaN(num) || num <= 0) return;

    // Instant client-side formula recompute (zero network calls)
    if (result && result.derived_values && result.lines.length > 0) {
      const avg = Number(result.derived_values.historical_daily_avg ?? 0);
      const stdDev = Number(result.derived_values.daily_std_dev ?? 0);
      const startDateStr = result.lines[0]?.points?.[0]?.date;

      const { baseline, expected, best, risk } = projectFitness(
        avg,
        stdDev,
        num,
        s2HorizonDays,
        startDateStr
      );

      setResult((prev) =>
        prev
          ? {
              ...prev,
              lines: [
                { label: "current_baseline", points: baseline },
                { label: "expected_case", points: expected },
                { label: "best_case", points: best },
                { label: "risk_case", points: risk },
              ],
              derived_values: {
                ...prev.derived_values,
                target_weekly_minutes: num,
                target_daily_minutes: Math.round((num / 7) * 100) / 100,
              },
            }
          : null
      );
    }

    // Debounced POST carries full params for recommendations
    triggerDebouncedPost("fitness_plan", {
      target_weekly_minutes: num,
      horizon_days: s2HorizonDays,
      ...(s2HistoryDays != null ? { history_days: s2HistoryDays } : {}),
    });
  }

  function handleS2HorizonChange(days: number) {
    setS2HorizonDays(days);
    if (days < 7 || days > 365) return;

    const targetNum = parseFloat(targetWeeklyMinutes) || 150;

    // Instant client-side formula recompute (zero network calls)
    if (result && result.derived_values && result.lines.length > 0) {
      const avg = Number(result.derived_values.historical_daily_avg ?? 0);
      const stdDev = Number(result.derived_values.daily_std_dev ?? 0);
      const startDateStr = result.lines[0]?.points?.[0]?.date;

      const { baseline, expected, best, risk } = projectFitness(
        avg,
        stdDev,
        targetNum,
        days,
        startDateStr
      );

      setResult((prev) =>
        prev
          ? {
              ...prev,
              lines: [
                { label: "current_baseline", points: baseline },
                { label: "expected_case", points: expected },
                { label: "best_case", points: best },
                { label: "risk_case", points: risk },
              ],
              derived_values: {
                ...prev.derived_values,
                horizon_days: days,
              },
            }
          : null
      );
    }

    // Debounced POST
    triggerDebouncedPost("fitness_plan", {
      target_weekly_minutes: targetNum,
      horizon_days: days,
      ...(s2HistoryDays != null ? { history_days: s2HistoryDays } : {}),
    });
  }

  function handleS2HistoryChange(history: number | null) {
    setS2HistoryDays(history);
    const targetNum = parseFloat(targetWeeklyMinutes) || 150;

    // History window changed: triggers debounced POST to re-analyze baseline history
    triggerDebouncedPost("fitness_plan", {
      target_weekly_minutes: targetNum,
      horizon_days: s2HorizonDays,
      ...(history != null ? { history_days: history } : {}),
    });
  }

  // CC1: S3 live controls & filters
  function handleS3FilterChange(newWindow?: number, newSubject?: string, newType?: string) {
    const w = newWindow !== undefined ? newWindow : s3WindowDays;
    const s = newSubject !== undefined ? newSubject : s3Subject;
    const t = newType !== undefined ? newType : s3AssessmentType;

    if (newWindow !== undefined) setS3WindowDays(w);
    if (newSubject !== undefined) setS3Subject(s);
    if (newType !== undefined) setS3AssessmentType(t);

    triggerDebouncedPost("reduce_study_hours", {
      window_days: w,
      ...(s ? { subject: s } : {}),
      ...(t ? { assessment_type: t } : {}),
      current_daily_hours: s3CurrentDailyHours,
      simulated_daily_hours: s3SimulatedDailyHours,
    });
  }

  function handleS3CurrentHoursChange(val: number) {
    setS3CurrentDailyHours(val);
    triggerDebouncedPost("reduce_study_hours", {
      window_days: s3WindowDays,
      ...(s3Subject ? { subject: s3Subject } : {}),
      ...(s3AssessmentType ? { assessment_type: s3AssessmentType } : {}),
      current_daily_hours: val,
      simulated_daily_hours: s3SimulatedDailyHours,
    });
  }

  function handleS3SimulatedHoursChange(val: number) {
    setS3SimulatedDailyHours(val);
    triggerDebouncedPost("reduce_study_hours", {
      window_days: s3WindowDays,
      ...(s3Subject ? { subject: s3Subject } : {}),
      ...(s3AssessmentType ? { assessment_type: s3AssessmentType } : {}),
      current_daily_hours: s3CurrentDailyHours,
      simulated_daily_hours: val,
    });
  }

  // ── CLIENT-SIDE VALIDATION ──────────────────────────────────────

  function validateParams(): Record<string, string> | null {
    const errs: Record<string, string> = {};

    if (selectedScenario === "increase_savings_rate") {
      const v = parseFloat(targetRate);
      if (isNaN(v) || v <= 0 || v > 100) errs.target_rate = "Rate must be between 0.01% and 100%.";
    } else if (selectedScenario === "fitness_plan") {
      const v = parseFloat(targetWeeklyMinutes);
      if (isNaN(v) || v <= 0) errs.target_weekly_minutes = "Target must be a positive number.";
      if (s2HorizonDays < 7 || s2HorizonDays > 365) errs.horizon_days = "Horizon must be between 7 and 365 days.";
    } else if (selectedScenario === "reduce_study_hours") {
      if (s3WindowDays !== 7 && s3WindowDays !== 14) errs.window_days = "Window must be 7 or 14 days.";
      if (s3CurrentDailyHours < 0 || s3CurrentDailyHours > 8) errs.current_daily_hours = "Hours must be between 0 and 8.";
      if (s3SimulatedDailyHours < 0 || s3SimulatedDailyHours > 8) errs.simulated_daily_hours = "Hours must be between 0 and 8.";
    } else if (selectedScenario === "buy_vs_rent") {
      const p = bvrParams;
      const hp = parseFloat(p.home_price);
      if (isNaN(hp) || hp <= 0) errs.home_price = "Must be a positive number.";

      const dp = parseFloat(p.down_payment_pct);
      if (isNaN(dp) || dp < 0 || dp > 100) errs.down_payment_pct = "Must be between 0% and 100%.";

      const mr = parseFloat(p.mortgage_rate_pct);
      if (isNaN(mr) || mr < 0 || mr > 30) errs.mortgage_rate_pct = "Must be between 0% and 30%.";

      const lt = parseInt(p.loan_term_years);
      if (isNaN(lt) || lt < 1 || lt > 40) errs.loan_term_years = "Must be between 1 and 40 years.";

      const rent = parseFloat(p.current_monthly_rent);
      if (isNaN(rent) || rent <= 0) errs.current_monthly_rent = "Must be a positive number.";

      const rentInc = parseFloat(p.expected_rent_increase_pct_per_year);
      if (isNaN(rentInc) || rentInc < 0 || rentInc > 30) errs.expected_rent_increase_pct_per_year = "Must be between 0% and 30%.";

      const apprec = parseFloat(p.expected_home_appreciation_pct_per_year);
      if (isNaN(apprec) || apprec < -10 || apprec > 30) errs.expected_home_appreciation_pct_per_year = "Must be between -10% and 30%.";

      const invRet = parseFloat(p.expected_investment_return_pct_per_year);
      if (isNaN(invRet) || invRet < 0 || invRet > 40) errs.expected_investment_return_pct_per_year = "Must be between 0% and 40%.";

      const depMonths = parseFloat(p.security_deposit_months);
      if (isNaN(depMonths) || depMonths < 0 || depMonths > 24) errs.security_deposit_months = "Must be between 0 and 24 months.";

      const closing = parseFloat(p.closing_costs_pct);
      if (isNaN(closing) || closing < 0 || closing > 20) errs.closing_costs_pct = "Must be between 0% and 20%.";

      const maint = parseFloat(p.maintenance_pct_per_year);
      if (isNaN(maint) || maint < 0 || maint > 20) errs.maintenance_pct_per_year = "Must be between 0% and 20%.";

      const tax = parseFloat(p.property_tax_pct_per_year);
      if (isNaN(tax) || tax < 0 || tax > 20) errs.property_tax_pct_per_year = "Must be between 0% and 20%.";

      const sell = parseFloat(p.selling_costs_pct);
      if (isNaN(sell) || sell < 0 || sell > 30) errs.selling_costs_pct = "Must be between 0% and 30%.";

      const infl = parseFloat(p.inflation_pct_per_year);
      if (isNaN(infl) || infl < -5 || infl > 30) errs.inflation_pct_per_year = "Must be between -5% and 30%.";

      const portTax = parseFloat(p.portfolio_gains_tax_pct);
      if (isNaN(portTax) || portTax < 0 || portTax > 60) errs.portfolio_gains_tax_pct = "Must be between 0% and 60%.";

      const propTax = parseFloat(p.property_gains_tax_pct);
      if (isNaN(propTax) || propTax < 0 || propTax > 60) errs.property_gains_tax_pct = "Must be between 0% and 60%.";

      const horiz = parseInt(p.horizon_years);
      if (isNaN(horiz) || horiz < 1 || horiz > 40) errs.horizon_years = "Must be between 1 and 40 years.";

      // Check D0 vs K
      if (!isNaN(hp) && !isNaN(dp) && !isNaN(closing) && !isNaN(depMonths) && !isNaN(rent)) {
        const k = (dp / 100 * hp) + (closing / 100 * hp);
        const d0 = depMonths * rent;
        if (d0 > k) {
          errs.security_deposit_months = `Deposit (₹${Math.round(d0).toLocaleString()}) cannot exceed initial capital (₹${Math.round(k).toLocaleString()}).`;
        }
      }
    } else if (selectedScenario === "program_outcome") {
      const p = poParams;
      const salary = parseFloat(p.current_annual_salary);
      if (!p.current_annual_salary.trim() || isNaN(salary) || salary <= 0) {
        errs.current_annual_salary = "Must be a positive number.";
      }
      const tuition = parseFloat(p.program_tuition_cost);
      if (!p.program_tuition_cost.trim() || isNaN(tuition) || tuition <= 0) {
        errs.program_tuition_cost = "Must be a positive number.";
      }
      const dur = parseFloat(p.program_duration_years);
      if (!p.program_duration_years.trim() || isNaN(dur) || dur < 0.5 || dur > 10.0) {
        errs.program_duration_years = "Must be between 0.5 and 10 years.";
      }
      const postSalary = parseFloat(p.expected_salary_post_program);
      if (!p.expected_salary_post_program.trim() || isNaN(postSalary) || postSalary <= 0) {
        errs.expected_salary_post_program = "Must be a positive number.";
      }
      const opp = parseFloat(p.opportunity_cost_income_during_program);
      if (!p.opportunity_cost_income_during_program.trim() || isNaN(opp) || opp < 0) {
        errs.opportunity_cost_income_during_program = "Must be zero or positive.";
      }
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
    stopPolling(false);

    let params: Record<string, unknown> = {};

    switch (selectedScenario) {
      case "increase_savings_rate":
        params = {
          target_rate: parseFloat(targetRate) / 100,
          horizon_months: s1HorizonMonths,
          ...(s1WindowStart ? { window_start: s1WindowStart } : {}),
          ...(s1WindowEnd ? { window_end: s1WindowEnd } : {}),
        };
        break;
      case "fitness_plan":
        params = {
          target_weekly_minutes: parseFloat(targetWeeklyMinutes),
          horizon_days: s2HorizonDays,
          ...(s2HistoryDays != null ? { history_days: s2HistoryDays } : {}),
        };
        break;
      case "reduce_study_hours":
        params = {
          window_days: s3WindowDays,
          ...(s3Subject ? { subject: s3Subject } : {}),
          ...(s3AssessmentType ? { assessment_type: s3AssessmentType } : {}),
          current_daily_hours: s3CurrentDailyHours,
          simulated_daily_hours: s3SimulatedDailyHours,
        };
        break;
      case "buy_vs_rent":
        params = {
          home_price: parseFloat(bvrParams.home_price),
          down_payment_pct: parseFloat(bvrParams.down_payment_pct),
          expected_home_appreciation_pct_per_year: parseFloat(bvrParams.expected_home_appreciation_pct_per_year),
          maintenance_pct_per_year: parseFloat(bvrParams.maintenance_pct_per_year),
          property_tax_pct_per_year: parseFloat(bvrParams.property_tax_pct_per_year),
          selling_costs_pct: parseFloat(bvrParams.selling_costs_pct),
          mortgage_rate_pct: parseFloat(bvrParams.mortgage_rate_pct),
          loan_term_years: parseInt(bvrParams.loan_term_years),
          closing_costs_pct: parseFloat(bvrParams.closing_costs_pct),
          current_monthly_rent: parseFloat(bvrParams.current_monthly_rent),
          expected_rent_increase_pct_per_year: parseFloat(bvrParams.expected_rent_increase_pct_per_year),
          security_deposit_months: parseFloat(bvrParams.security_deposit_months),
          expected_investment_return_pct_per_year: parseFloat(bvrParams.expected_investment_return_pct_per_year),
          inflation_pct_per_year: parseFloat(bvrParams.inflation_pct_per_year),
          output_basis: bvrParams.output_basis,
          portfolio_gains_tax_pct: parseFloat(bvrParams.portfolio_gains_tax_pct),
          property_gains_tax_pct: parseFloat(bvrParams.property_gains_tax_pct),
          horizon_years: parseInt(bvrParams.horizon_years || bvrParams.loan_term_years),
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

      if (res.scenario_type === "increase_savings_rate" && res.derived_values) {
        if (res.derived_values.window_start && !s1WindowStart) {
          setS1WindowStart(String(res.derived_values.window_start));
        }
        if (res.derived_values.window_end && !s1WindowEnd) {
          setS1WindowEnd(String(res.derived_values.window_end));
        }
        if (res.derived_values.horizon_months) {
          setS1HorizonMonths(Number(res.derived_values.horizon_months));
        }
      } else if (res.scenario_type === "fitness_plan" && res.derived_values) {
        if (res.derived_values.horizon_days) {
          setS2HorizonDays(Number(res.derived_values.horizon_days));
        }
      } else if (res.scenario_type === "reduce_study_hours" && res.derived_values) {
        if (res.derived_values.window_days) {
          setS3WindowDays(Number(res.derived_values.window_days));
        }
        if (res.derived_values.observed_avg_daily_hours != null && s3CurrentDailyHours === 2.0) {
          setS3CurrentDailyHours(Number(res.derived_values.observed_avg_daily_hours));
        }
      }

      // Start polling for recommendations if pending
      if (res.recommendations_status === "pending") {
        startPolling(res.id);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 422 && err.detail) {
          const fErrs = extractFieldErrors(err.detail);
          if (Object.keys(fErrs).length > 0) {
            setFieldErrors(fErrs);
            return;
          }
        }
        setError(err.message || "Something went wrong. Please try again.");
      } else if (err && typeof err === "object" && "status" in err) {
        const apiErr = err as { status: number; message?: string; detail?: unknown };
        if (apiErr.status === 422 && apiErr.detail) {
          const fErrs = extractFieldErrors(apiErr.detail);
          if (Object.keys(fErrs).length > 0) {
            setFieldErrors(fErrs);
            return;
          }
        }
        setError(apiErr.message || "Something went wrong. Please try again.");
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
            stopPolling(false);
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

            {/* Scenario 1: Increase Savings Rate */}
            {selectedScenario === "increase_savings_rate" && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Target Savings Rate */}
                  <div>
                    <Field
                      label={`Target Savings Rate: ${targetRate}%`}
                      error={fieldErrors.target_rate}
                      hint="Percentage of monthly income to save (1% – 100%)"
                    >
                      <div className="space-y-2">
                        <input
                          type="range"
                          min="1"
                          max="100"
                          step="1"
                          value={targetRate}
                          onChange={(e) => handleS1TargetRateChange(e.target.value)}
                          className="w-full accent-primary cursor-pointer"
                        />
                        <Input
                          type="number"
                          value={targetRate}
                          onChange={(e) => handleS1TargetRateChange(e.target.value)}
                          placeholder="e.g. 25"
                          min={0.01}
                          max={100}
                          step={0.5}
                          invalid={!!fieldErrors.target_rate}
                        />
                      </div>
                    </Field>
                  </div>

                  {/* Projection Horizon */}
                  <div>
                    <Field
                      label={`Projection Horizon: ${s1HorizonMonths} months (${(s1HorizonMonths / 12).toFixed(1)} yrs)`}
                      error={fieldErrors.horizon_months}
                      hint="1 to 120 months"
                    >
                      <div className="space-y-2">
                        <input
                          type="range"
                          min="1"
                          max="120"
                          step="1"
                          value={s1HorizonMonths}
                          onChange={(e) => handleS1HorizonChange(parseInt(e.target.value) || 1)}
                          className="w-full accent-primary cursor-pointer"
                        />
                        <Input
                          type="number"
                          value={s1HorizonMonths}
                          onChange={(e) => handleS1HorizonChange(parseInt(e.target.value) || 1)}
                          min={1}
                          max={120}
                          step={1}
                          invalid={!!fieldErrors.horizon_months}
                        />
                      </div>
                    </Field>
                  </div>
                </div>

                {/* Analysis Date Window */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-line/60">
                  <Field
                    label="Analysis Window Start"
                    error={fieldErrors.window_start}
                    hint="Earliest income entry date used"
                  >
                    <Input
                      type="date"
                      value={s1WindowStart}
                      max={s1WindowEnd || new Date().toISOString().slice(0, 10)}
                      onChange={(e) => handleS1WindowChange(e.target.value, s1WindowEnd)}
                      invalid={!!fieldErrors.window_start}
                    />
                  </Field>
                  <Field
                    label="Analysis Window End"
                    error={fieldErrors.window_end}
                    hint="Latest date (up to today)"
                  >
                    <Input
                      type="date"
                      value={s1WindowEnd}
                      min={s1WindowStart}
                      max={new Date().toISOString().slice(0, 10)}
                      onChange={(e) => handleS1WindowChange(s1WindowStart, e.target.value)}
                      invalid={!!fieldErrors.window_end}
                    />
                  </Field>
                </div>
              </div>
            )}

            {/* Scenario 2: Fitness Plan */}
            {selectedScenario === "fitness_plan" && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Target Weekly Minutes */}
                  <div>
                    <Field
                      label={`Target Weekly Minutes: ${targetWeeklyMinutes} min/wk`}
                      error={fieldErrors.target_weekly_minutes}
                      hint={`~${((parseFloat(targetWeeklyMinutes) || 0) / 7).toFixed(1)} min/day`}
                    >
                      <div className="space-y-2">
                        <input
                          type="range"
                          min="10"
                          max="1000"
                          step="10"
                          value={targetWeeklyMinutes}
                          onChange={(e) => handleS2TargetChange(e.target.value)}
                          className="w-full accent-primary cursor-pointer"
                        />
                        <Input
                          type="number"
                          value={targetWeeklyMinutes}
                          onChange={(e) => handleS2TargetChange(e.target.value)}
                          placeholder="e.g. 150"
                          min={1}
                          step={5}
                          invalid={!!fieldErrors.target_weekly_minutes}
                        />
                      </div>
                    </Field>
                  </div>

                  {/* Projection Horizon */}
                  <div>
                    <Field
                      label={`Projection Horizon: ${s2HorizonDays} days (${(s2HorizonDays / 30).toFixed(1)} mo)`}
                      error={fieldErrors.horizon_days}
                      hint="7 to 365 days"
                    >
                      <div className="space-y-2">
                        <input
                          type="range"
                          min="7"
                          max="365"
                          step="1"
                          value={s2HorizonDays}
                          onChange={(e) => handleS2HorizonChange(parseInt(e.target.value) || 7)}
                          className="w-full accent-primary cursor-pointer"
                        />
                        <Input
                          type="number"
                          value={s2HorizonDays}
                          onChange={(e) => handleS2HorizonChange(parseInt(e.target.value) || 7)}
                          min={7}
                          max={365}
                          step={1}
                          invalid={!!fieldErrors.horizon_days}
                        />
                      </div>
                    </Field>
                  </div>
                </div>

                {/* History Window Filter */}
                <div className="pt-2 border-t border-line/60">
                  <p className="text-[12px] font-semibold text-ink mb-2">History Window for Baseline Pace</p>
                  <div className="flex items-center gap-2">
                    {[
                      { label: "30 Days", val: 30 },
                      { label: "60 Days", val: 60 },
                      { label: "90 Days", val: 90 },
                      { label: "All Time", val: null },
                    ].map((opt) => {
                      const isSelected = s2HistoryDays === opt.val;
                      return (
                        <button
                          key={opt.label}
                          type="button"
                          onClick={() => handleS2HistoryChange(opt.val)}
                          className={`px-3 py-1.5 rounded-lg text-[12px] font-medium transition-all ${
                            isSelected
                              ? "bg-primary text-white shadow-xs"
                              : "bg-bg-soft text-ink-soft hover:text-ink hover:bg-bg-soft/80 border border-line"
                          }`}
                        >
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {selectedScenario === "reduce_study_hours" && (
              <div className="space-y-4">
                {/* Filters Row: Window, Subject, Assessment Type */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3 rounded-lg bg-bg-soft/60 border border-line">
                  <Field label="Aggregation Window" hint="Prior study days" error={fieldErrors.window_days}>
                    <div className="flex gap-1.5 mt-1">
                      <button
                        type="button"
                        onClick={() => handleS3FilterChange(14, undefined, undefined)}
                        className={`flex-1 py-1.5 px-2 rounded-md text-[12px] font-semibold transition-all ${
                          s3WindowDays === 14
                            ? "bg-primary text-white shadow-xs"
                            : "bg-card text-ink-soft hover:text-ink border border-line"
                        }`}
                      >
                        14 Days (Standard)
                      </button>
                      <button
                        type="button"
                        onClick={() => handleS3FilterChange(7, undefined, undefined)}
                        className={`flex-1 py-1.5 px-2 rounded-md text-[12px] font-semibold transition-all ${
                          s3WindowDays === 7
                            ? "bg-primary text-white shadow-xs"
                            : "bg-card text-ink-soft hover:text-ink border border-line"
                        }`}
                      >
                        7 Days (Short)
                      </button>
                    </div>
                  </Field>

                  <Field label="Subject / Course" hint="Filter by course">
                    <Select
                      value={s3Subject}
                      onChange={(e) => handleS3FilterChange(undefined, e.target.value, undefined)}
                    >
                      <option value="">All Subjects (Pooled)</option>
                      {((result?.derived_values?.available_subjects as string[]) || []).map((subj) => (
                        <option key={subj} value={subj}>
                          {subj}
                        </option>
                      ))}
                    </Select>
                  </Field>

                  <Field label="Assessment Type" hint="Filter by exam type">
                    <Select
                      value={s3AssessmentType}
                      onChange={(e) => handleS3FilterChange(undefined, undefined, e.target.value)}
                    >
                      <option value="">All Types (Pooled)</option>
                      {((result?.derived_values?.available_assessment_types as string[]) || []).map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>

                {/* Sliders Row: Baseline Routine & Simulated Routine */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-3 rounded-lg border border-line/80 bg-card/50">
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-[12.5px] font-semibold text-ink flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block"></span>
                        Current Routine (Baseline)
                      </label>
                      <span className="text-[13px] font-bold text-ink font-mono">
                        {s3CurrentDailyHours.toFixed(2)} hrs/day
                      </span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="8"
                      step="0.25"
                      value={s3CurrentDailyHours}
                      onChange={(e) => handleS3CurrentHoursChange(parseFloat(e.target.value))}
                      className="w-full accent-red-500 cursor-pointer"
                    />
                    <div className="flex justify-between text-[10px] text-ink-faint mt-1">
                      <span>0h (No study)</span>
                      <span>4h</span>
                      <span>8h (Intensive)</span>
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-[12.5px] font-semibold text-ink flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block"></span>
                        Simulated Routine (Target)
                      </label>
                      <span className="text-[13px] font-bold text-ink font-mono">
                        {s3SimulatedDailyHours.toFixed(2)} hrs/day
                      </span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="8"
                      step="0.25"
                      value={s3SimulatedDailyHours}
                      onChange={(e) => handleS3SimulatedHoursChange(parseFloat(e.target.value))}
                      className="w-full accent-emerald-500 cursor-pointer"
                    />
                    <div className="flex justify-between text-[10px] text-ink-faint mt-1">
                      <span>0h (No study)</span>
                      <span>4h</span>
                      <span>8h (Intensive)</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Scenario 4: Buy vs Rent (4 Structured Sections) */}
            {selectedScenario === "buy_vs_rent" && (
              <div className="space-y-5">
                <div className="flex items-center justify-between gap-2 p-2.5 rounded-lg bg-bg-soft/70 border border-line">
                  <div className="flex items-center gap-2 text-[12px] text-ink-soft">
                    <I name="info" size={14} className="text-primary shrink-0" />
                    <span>Compare long-term property equity against an invested rental portfolio.</span>
                  </div>
                  <Chip tone="warn" className="text-[10px] shrink-0 font-medium">
                    Editable illustrative assumptions
                  </Chip>
                </div>

                {/* Section 1: Purchase */}
                <div className="space-y-2.5">
                  <h4 className="text-[12.5px] font-bold text-ink uppercase tracking-wider flex items-center gap-1.5">
                    <I name="home" size={13} className="text-primary" />
                    1. Purchase Assumptions
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <Field label="Home Price (₹)" error={fieldErrors.home_price}>
                      <Input
                        type="number"
                        value={bvrParams.home_price}
                        onChange={(e) => setBvrParams((p) => ({ ...p, home_price: e.target.value }))}
                        placeholder="5000000"
                        invalid={!!fieldErrors.home_price}
                      />
                    </Field>
                    <Field label="Down Payment (%)" error={fieldErrors.down_payment_pct} hint="0% – 100%">
                      <Input
                        type="number"
                        value={bvrParams.down_payment_pct}
                        onChange={(e) => setBvrParams((p) => ({ ...p, down_payment_pct: e.target.value }))}
                        placeholder="20"
                        min={0}
                        max={100}
                        step={1}
                        invalid={!!fieldErrors.down_payment_pct}
                      />
                    </Field>
                    <Field label="Home Appreciation (%/yr)" error={fieldErrors.expected_home_appreciation_pct_per_year} hint="-10% – 30%">
                      <Input
                        type="number"
                        value={bvrParams.expected_home_appreciation_pct_per_year}
                        onChange={(e) => setBvrParams((p) => ({ ...p, expected_home_appreciation_pct_per_year: e.target.value }))}
                        placeholder="7"
                        step={0.5}
                        invalid={!!fieldErrors.expected_home_appreciation_pct_per_year}
                      />
                    </Field>
                    <Field label="Annual Maintenance (%)" error={fieldErrors.maintenance_pct_per_year} hint="0% – 20% of value">
                      <Input
                        type="number"
                        value={bvrParams.maintenance_pct_per_year}
                        onChange={(e) => setBvrParams((p) => ({ ...p, maintenance_pct_per_year: e.target.value }))}
                        placeholder="1"
                        step={0.5}
                        invalid={!!fieldErrors.maintenance_pct_per_year}
                      />
                    </Field>
                    <Field label="Property Tax (%/yr)" error={fieldErrors.property_tax_pct_per_year} hint="0% – 20% of value">
                      <Input
                        type="number"
                        value={bvrParams.property_tax_pct_per_year}
                        onChange={(e) => setBvrParams((p) => ({ ...p, property_tax_pct_per_year: e.target.value }))}
                        placeholder="1"
                        step={0.5}
                        invalid={!!fieldErrors.property_tax_pct_per_year}
                      />
                    </Field>
                    <Field label="Selling Costs on Exit (%)" error={fieldErrors.selling_costs_pct} hint="0% – 30% of value">
                      <Input
                        type="number"
                        value={bvrParams.selling_costs_pct}
                        onChange={(e) => setBvrParams((p) => ({ ...p, selling_costs_pct: e.target.value }))}
                        placeholder="6"
                        step={0.5}
                        invalid={!!fieldErrors.selling_costs_pct}
                      />
                    </Field>
                  </div>
                </div>

                {/* Section 2: Mortgage */}
                <div className="space-y-2.5 pt-2 border-t border-line/50">
                  <h4 className="text-[12.5px] font-bold text-ink uppercase tracking-wider flex items-center gap-1.5">
                    <I name="credit-card" size={13} className="text-primary" />
                    2. Mortgage & Financing
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <Field label="Mortgage Rate (%/yr)" error={fieldErrors.mortgage_rate_pct} hint="0% – 30%">
                      <Input
                        type="number"
                        value={bvrParams.mortgage_rate_pct}
                        onChange={(e) => setBvrParams((p) => ({ ...p, mortgage_rate_pct: e.target.value }))}
                        placeholder="8.5"
                        step={0.1}
                        invalid={!!fieldErrors.mortgage_rate_pct}
                      />
                    </Field>
                    <Field label="Loan Term (Years)" error={fieldErrors.loan_term_years} hint="1 – 40 years">
                      <Input
                        type="number"
                        value={bvrParams.loan_term_years}
                        onChange={(e) => setBvrParams((p) => ({ ...p, loan_term_years: e.target.value }))}
                        placeholder="20"
                        min={1}
                        max={40}
                        invalid={!!fieldErrors.loan_term_years}
                      />
                    </Field>
                    <Field label="Closing Costs at t0 (%)" error={fieldErrors.closing_costs_pct} hint="0% – 20% of price">
                      <Input
                        type="number"
                        value={bvrParams.closing_costs_pct}
                        onChange={(e) => setBvrParams((p) => ({ ...p, closing_costs_pct: e.target.value }))}
                        placeholder="3"
                        step={0.5}
                        invalid={!!fieldErrors.closing_costs_pct}
                      />
                    </Field>
                  </div>
                </div>

                {/* Section 3: Rental */}
                <div className="space-y-2.5 pt-2 border-t border-line/50">
                  <h4 className="text-[12.5px] font-bold text-ink uppercase tracking-wider flex items-center gap-1.5">
                    <I name="calendar" size={13} className="text-primary" />
                    3. Rental Assumptions
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <Field label="Initial Monthly Rent (₹)" error={fieldErrors.current_monthly_rent}>
                      <Input
                        type="number"
                        value={bvrParams.current_monthly_rent}
                        onChange={(e) => setBvrParams((p) => ({ ...p, current_monthly_rent: e.target.value }))}
                        placeholder="25000"
                        invalid={!!fieldErrors.current_monthly_rent}
                      />
                    </Field>
                    <Field label="Annual Rent Increase (%)" error={fieldErrors.expected_rent_increase_pct_per_year} hint="0% – 30%">
                      <Input
                        type="number"
                        value={bvrParams.expected_rent_increase_pct_per_year}
                        onChange={(e) => setBvrParams((p) => ({ ...p, expected_rent_increase_pct_per_year: e.target.value }))}
                        placeholder="5"
                        step={0.5}
                        invalid={!!fieldErrors.expected_rent_increase_pct_per_year}
                      />
                    </Field>
                    <Field label="Security Deposit (Months)" error={fieldErrors.security_deposit_months} hint="Refundable (0 – 24 mo)">
                      <Input
                        type="number"
                        value={bvrParams.security_deposit_months}
                        onChange={(e) => setBvrParams((p) => ({ ...p, security_deposit_months: e.target.value }))}
                        placeholder="2"
                        step={0.5}
                        invalid={!!fieldErrors.security_deposit_months}
                      />
                    </Field>
                  </div>
                </div>

                {/* Section 4: Investment, Tax & Horizon */}
                <div className="space-y-2.5 pt-2 border-t border-line/50">
                  <h4 className="text-[12.5px] font-bold text-ink uppercase tracking-wider flex items-center gap-1.5">
                    <I name="chart" size={13} className="text-primary" />
                    4. Investment, Tax & Horizon
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <Field label="Investment Return (%/yr)" error={fieldErrors.expected_investment_return_pct_per_year} hint="0% – 40%">
                      <Input
                        type="number"
                        value={bvrParams.expected_investment_return_pct_per_year}
                        onChange={(e) => setBvrParams((p) => ({ ...p, expected_investment_return_pct_per_year: e.target.value }))}
                        placeholder="12"
                        step={0.5}
                        invalid={!!fieldErrors.expected_investment_return_pct_per_year}
                      />
                    </Field>
                    <Field label="Annual Inflation (%/yr)" error={fieldErrors.inflation_pct_per_year} hint="-5% – 30%">
                      <Input
                        type="number"
                        value={bvrParams.inflation_pct_per_year}
                        onChange={(e) => setBvrParams((p) => ({ ...p, inflation_pct_per_year: e.target.value }))}
                        placeholder="5"
                        step={0.5}
                        invalid={!!fieldErrors.inflation_pct_per_year}
                      />
                    </Field>
                    <Field label="Projection Horizon (Years)" error={fieldErrors.horizon_years} hint="1 – 40 years">
                      <Input
                        type="number"
                        value={bvrParams.horizon_years}
                        onChange={(e) => setBvrParams((p) => ({ ...p, horizon_years: e.target.value }))}
                        placeholder="20"
                        min={1}
                        max={40}
                        invalid={!!fieldErrors.horizon_years}
                      />
                    </Field>
                    <Field label="Portfolio Gains Tax (%)" error={fieldErrors.portfolio_gains_tax_pct} hint="0% – 60%">
                      <Input
                        type="number"
                        value={bvrParams.portfolio_gains_tax_pct}
                        onChange={(e) => setBvrParams((p) => ({ ...p, portfolio_gains_tax_pct: e.target.value }))}
                        placeholder="0"
                        min={0}
                        max={60}
                        step={1}
                        invalid={!!fieldErrors.portfolio_gains_tax_pct}
                      />
                    </Field>
                    <Field label="Property Gains Tax (%)" error={fieldErrors.property_gains_tax_pct} hint="0% – 60%">
                      <Input
                        type="number"
                        value={bvrParams.property_gains_tax_pct}
                        onChange={(e) => setBvrParams((p) => ({ ...p, property_gains_tax_pct: e.target.value }))}
                        placeholder="0"
                        min={0}
                        max={60}
                        step={1}
                        invalid={!!fieldErrors.property_gains_tax_pct}
                      />
                    </Field>
                    <Field label="Output Basis" hint="Nominal vs Inflation-Adjusted">
                      <div className="flex items-center gap-1.5 mt-1">
                        <button
                          type="button"
                          onClick={() => setBvrParams((p) => ({ ...p, output_basis: "nominal" }))}
                          className={`flex-1 py-2 rounded-lg text-[12px] font-semibold transition-all ${
                            bvrParams.output_basis === "nominal"
                              ? "bg-primary text-white shadow-xs"
                              : "bg-bg-soft text-ink-soft hover:text-ink border border-line"
                          }`}
                        >
                          Nominal
                        </button>
                        <button
                          type="button"
                          onClick={() => setBvrParams((p) => ({ ...p, output_basis: "real" }))}
                          className={`flex-1 py-2 rounded-lg text-[12px] font-semibold transition-all ${
                            bvrParams.output_basis === "real"
                              ? "bg-primary text-white shadow-xs"
                              : "bg-bg-soft text-ink-soft hover:text-ink border border-line"
                          }`}
                        >
                          Real (Deflated)
                        </button>
                      </div>
                    </Field>
                  </div>
                </div>
              </div>
            )}

            {/* Program Outcome: 5 fields */}
            {selectedScenario === "program_outcome" && (
              <div className="space-y-4">
                {/* Pinned, non-dismissible disclosure (D8) */}
                <div
                  data-testid="hypothetical-disclosure"
                  className="rounded-lg bg-amber-500/10 border border-amber-500/25 p-3 flex items-start gap-2.5 text-amber-800 dark:text-amber-300 text-[12px] leading-relaxed"
                >
                  <I name="info" size={15} className="shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
                  <span>These projections are based on the hypothetical numbers you enter here, not your tracked data.</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {[
                    { key: "current_annual_salary", label: "Current Annual Salary (₹)", placeholder: "e.g. 500000" },
                    { key: "program_tuition_cost", label: "Program Tuition Cost (₹)", placeholder: "e.g. 200000" },
                    { key: "program_duration_years", label: "Program Duration (years)", placeholder: "e.g. 2", hint: "0.5–10 years" },
                    { key: "expected_salary_post_program", label: "Expected Salary Post-Program (₹)", placeholder: "e.g. 800000" },
                    {
                      key: "opportunity_cost_income_during_program",
                      label: "Extra Annual Cost While Enrolled (₹/yr)",
                      placeholder: "e.g. 0",
                      hint: "Extra annual cost while enrolled (beyond tuition). Leave at 0 unless you have additional costs.",
                    },
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
                <ScenarioBadge result={result} />
                <ProvenanceChip result={result} />
                {isUpdating && (
                  <span
                    data-testid="updating-indicator"
                    className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-medium bg-primary/10 text-primary animate-pulse ml-auto"
                  >
                    <I name="refresh" size={11} className="animate-spin" />
                    Updating…
                  </span>
                )}
              </div>

              {/* S3 instant client-side interpolation (CC1) */}
              {(() => {
                const s3ExpectedPoints =
                  result.scenario_type === "reduce_study_hours"
                    ? result.lines.find((l) => l.label === "expected_case")?.points || []
                    : [];

                const s3CurrentScore =
                  s3ExpectedPoints.length > 0
                    ? interpolateCurve(s3ExpectedPoints, s3CurrentDailyHours)
                    : Number(result.derived_values?.baseline_score ?? 0);

                const s3SimulatedScore =
                  s3ExpectedPoints.length > 0
                    ? interpolateCurve(s3ExpectedPoints, s3SimulatedDailyHours)
                    : Number(result.derived_values?.scenario_score ?? 0);

                const s3AbsDiff = s3SimulatedScore - s3CurrentScore;
                const s3RelDiff =
                  s3CurrentScore > 0 ? (s3AbsDiff / s3CurrentScore) * 100 : 0;

                return (
                  <>
                    {/* Derived values summary */}
                    {result.derived_values && (
                      <DerivedValuesSummary
                        result={result}
                        s3CurrentDailyHours={s3CurrentDailyHours}
                        s3SimulatedDailyHours={s3SimulatedDailyHours}
                        s3CurrentScore={s3CurrentScore}
                        s3SimulatedScore={s3SimulatedScore}
                        s3AbsDiff={s3AbsDiff}
                        s3RelDiff={s3RelDiff}
                      />
                    )}

                    {/* Chart */}
                    {result.lines.length > 0 &&
                    !(
                      result.scenario_type === "increase_savings_rate" &&
                      Number(result.derived_values?.avg_monthly_income ?? 0) <= 0
                    ) ? (
                      <>
                        <SimulationChart
                          result={result}
                          isDark={isDark}
                          s3CurrentDailyHours={s3CurrentDailyHours}
                          s3SimulatedDailyHours={s3SimulatedDailyHours}
                          s3CurrentScore={s3CurrentScore}
                          s3SimulatedScore={s3SimulatedScore}
                        />
                  {/* Built-in assumptions disclosure (PR1) */}
                  {result.scenario_type === "program_outcome" && result.message && (
                    <p
                      data-testid="program-assumptions-disclosure"
                      className="mt-3 text-[11.5px] text-ink-faint leading-relaxed italic border-l-2 border-primary/30 pl-3"
                    >
                      {result.message}
                    </p>
                  )}
                  {/* Savings rate warning (e.g. current savings rate > 100%) */}
                  {result.scenario_type === "increase_savings_rate" && result.message && (
                    <p
                      data-testid="savings-rate-warning"
                      className="mt-3 text-[11.5px] text-amber-700 dark:text-amber-400 bg-amber-500/10 border border-amber-500/25 rounded-md p-2.5 flex items-center gap-2"
                    >
                      <I name="alert" size={13} className="shrink-0" />
                      <span>{result.message}</span>
                    </p>
                  )}
                </>
              ) : (
                <div className="h-[200px] flex flex-col items-center justify-center rounded-lg bg-bg-soft/60 border border-dashed border-line text-center p-4">
                  <div className="w-8 h-8 rounded-full bg-warn-soft text-warn flex items-center justify-center mx-auto mb-2">
                    <I name="info" size={16} />
                  </div>
                  <p className="text-[13px] font-semibold text-ink mb-1">
                    {result.scenario_type === "increase_savings_rate" &&
                    Number(result.derived_values?.avg_monthly_income ?? 0) <= 0
                      ? "No Income in Window"
                      : "Insufficient Data"}
                  </p>
                  <p className="text-[11.5px] text-ink-soft max-w-[320px]">
                    {result.scenario_type === "increase_savings_rate" &&
                    Number(result.derived_values?.avg_monthly_income ?? 0) <= 0
                      ? "No income entries found in the selected date window. Please widen your date range or log income entries."
                      : result.message || "Not enough tracked data to generate a projection."}
                  </p>
                </div>
              )}
                  </>
                );
              })()}

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

function ScenarioBadge({ result }: { result: SimulationResponse }) {
  const isAssumption =
    result.scenario_type === "buy_vs_rent" ||
    result.scenario_type === "program_outcome" ||
    result.reliability === "assumption_based";

  if (isAssumption) {
    return (
      <span
        data-testid="assumption-badge"
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30 shadow-xs"
      >
        <I name="sliders" size={12} />
        Assumption-Based
      </span>
    );
  }

  const r = result.reliability;
  if (r === "reliable") {
    return (
      <Chip tone="ok">
        <I name="check" size={11} />
        Reliable ({result.data_point_count != null ? `${result.data_point_count} pts` : "6+ pts"})
      </Chip>
    );
  }

  if (r === "low_confidence") {
    return (
      <Chip tone="warn">
        <I name="alert" size={11} />
        Low Confidence ({result.data_point_count != null ? `${result.data_point_count} pts` : "3-5 pts"})
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
  // Buy vs Rent: affordability chip (D4 fix)
  if (result.scenario_type === "buy_vs_rent") {
    const dv = result.derived_values;
    const K = Number(dv?.initial_capital_required || 0);
    const S = Number(dv?.tracked_savings || 0);
    const coverage = Number(dv?.capital_coverage_pct || 0);
    return (
      <Chip tone="custom" className="bg-primary-soft/50 text-ink-soft border border-primary/15 text-[11px]">
        Initial capital required: {formatCompactINR(K)} · Tracked savings: {formatCompactINR(S)} ({coverage}% covered)
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

  // Fitness Plan: show current avg vs target
  if (
    result.scenario_type === "fitness_plan" &&
    result.derived_values
  ) {
    const dv = result.derived_values;
    const histAvgDaily = Number(dv.historical_daily_avg || 0);
    const targetWeekly = Number(dv.target_weekly_minutes || 0);
    return (
      <Chip tone="primary">
        Current: {(histAvgDaily * 7).toFixed(0)} min/wk → Target: {targetWeekly.toFixed(0)} min/wk
      </Chip>
    );
  }

  return null;
}

function DerivedValuesSummary({
  result,
  s3CurrentDailyHours,
  s3SimulatedDailyHours,
  s3CurrentScore,
  s3SimulatedScore,
  s3AbsDiff,
  s3RelDiff,
}: {
  result: SimulationResponse;
  s3CurrentDailyHours?: number;
  s3SimulatedDailyHours?: number;
  s3CurrentScore?: number;
  s3SimulatedScore?: number;
  s3AbsDiff?: number;
  s3RelDiff?: number;
}) {
  const dv = result.derived_values!;

  if (result.scenario_type === "increase_savings_rate") {
    const baseSavings = dv.base_savings != null ? Number(dv.base_savings) : 0;
    const avgMonthlyInc = dv.avg_monthly_income != null ? Number(dv.avg_monthly_income) : 0;
    const curRate = dv.current_rate != null ? Number(dv.current_rate) : 0;
    const tgtRate = dv.target_rate != null ? Number(dv.target_rate) : 0;
    const horizon = dv.horizon_months != null ? Number(dv.horizon_months) : 60;
    const totalInc = dv.total_income_in_window != null ? Number(dv.total_income_in_window) : 0;
    const totalSav = dv.total_savings_in_window != null ? Number(dv.total_savings_in_window) : 0;
    const monthsWin = dv.months_in_window != null ? Number(dv.months_in_window) : 0;

    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
        {[
          { label: "Base Savings (Current)", value: formatCurrency(baseSavings) },
          { label: "Avg Monthly Income", value: formatCurrency(avgMonthlyInc) },
          { label: "Current Savings Rate", value: `${(curRate * 100).toFixed(1)}%` },
          { label: "Target Savings Rate", value: `${(tgtRate * 100).toFixed(1)}%` },
          { label: "Horizon", value: `${horizon} months (${(horizon / 12).toFixed(1)}y)` },
          { label: "Income in Window", value: formatCurrency(totalInc) },
          { label: "Savings in Window", value: formatCurrency(totalSav) },
          { label: "Window Duration", value: `${monthsWin.toFixed(1)} months` },
        ].map((m) => (
          <div key={m.label} className="rounded-lg bg-bg-soft p-2.5">
            <p className="text-[10px] text-ink-faint uppercase tracking-wider">{m.label}</p>
            <p className="text-[13.5px] font-bold text-ink mt-0.5">{m.value}</p>
          </div>
        ))}
      </div>
    );
  }

  if (result.scenario_type === "fitness_plan") {
    const baselineLine = result.lines.find((l) => l.label === "current_baseline");
    const expectedLine = result.lines.find((l) => l.label === "expected_case");
    const bestLine = result.lines.find((l) => l.label === "best_case");
    const riskLine = result.lines.find((l) => l.label === "risk_case");

    const lastBaseline = baselineLine?.points?.[baselineLine.points.length - 1]?.value ?? 0;
    const lastExpected = expectedLine?.points?.[expectedLine.points.length - 1]?.value ?? 0;
    const lastBest = bestLine?.points?.[bestLine.points.length - 1]?.value ?? 0;
    const lastRisk = riskLine?.points?.[riskLine.points.length - 1]?.value ?? 0;

    const horizonDays = Number(dv.horizon_days || 90);
    const histAvgDaily = Number(dv.historical_daily_avg || 0);
    const targetWeekly = Number(dv.target_weekly_minutes || 0);

    return (
      <div className="space-y-3 mb-4">
        {/* Baseline & Target Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            { label: "Historical Baseline", value: `${(histAvgDaily * 7).toFixed(0)} min/wk` },
            { label: "Target Pace", value: `${targetWeekly.toFixed(0)} min/wk` },
            { label: "Daily Std Dev (σ)", value: `${Number(dv.daily_std_dev || 0).toFixed(1)} min/d` },
            { label: "History Window", value: `${dv.history_window_days || 0} days` },
          ].map((m) => (
            <div key={m.label} className="rounded-lg bg-bg-soft p-2.5">
              <p className="text-[10px] text-ink-faint uppercase tracking-wider">{m.label}</p>
              <p className="text-[13.5px] font-bold text-ink mt-0.5">{m.value}</p>
            </div>
          ))}
        </div>

        {/* Projected Horizon Total KPIs */}
        <div className="rounded-lg border border-line bg-card/60 p-3">
          <p className="text-[11px] font-semibold text-ink-faint uppercase tracking-wider mb-2">
            Projected Total Activity at Horizon ({horizonDays} Days)
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[
              { label: "Historical Baseline", value: `${Math.round(lastBaseline)} min` },
              { label: "Target Plan", value: `${Math.round(lastExpected)} min` },
              { label: "Best Case (+80% band)", value: `${Math.round(lastBest)} min` },
              { label: "Risk Case (-80% band)", value: `${Math.round(lastRisk)} min` },
            ].map((kpi) => (
              <div key={kpi.label} className="p-2 rounded bg-bg-soft/70">
                <p className="text-[10px] text-ink-faint">{kpi.label}</p>
                <p className="text-[14px] font-bold text-ink mt-0.5">{kpi.value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (result.scenario_type === "buy_vs_rent") {
    const initCapital = Number(dv.initial_capital_required || 0);
    const emi = Number(dv.monthly_emi || 0);
    const buyNet = Number(dv.buy_net_position || 0);
    const rentNet = Number(dv.rent_net_position || 0);
    const netDiff = Number(dv.net_difference || 0);
    const totalRent = Number(dv.total_rent_paid || 0);
    const totalInterest = Number(dv.total_interest_paid || 0);
    const breakEven =
      dv.break_even_year != null
        ? `Year ${Number(dv.break_even_year).toFixed(1)}`
        : "Does not break even";
    const horizon = Number(dv.horizon_years || 20);

    return (
      <div className="space-y-3 mb-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            { label: "Initial Capital (K)", value: formatCompactINR(initCapital) },
            { label: "Monthly Mortgage EMI", value: formatCurrency(emi) },
            { label: `Final Buy Net Worth (${horizon}y)`, value: formatCompactINR(buyNet) },
            { label: `Final Rent Net Worth (${horizon}y)`, value: formatCompactINR(rentNet) },
            {
              label: "Net Difference (Buy − Rent)",
              value: `${netDiff >= 0 ? "+" : ""}${formatCompactINR(netDiff)}`,
              highlight: netDiff >= 0 ? "text-emerald-500" : "text-amber-500",
            },
            { label: "Break-Even Point", value: breakEven },
            { label: "Total Rent Paid", value: formatCompactINR(totalRent) },
            { label: "Total Interest Paid", value: formatCompactINR(totalInterest) },
          ].map((m) => (
            <div key={m.label} className="rounded-lg bg-bg-soft p-2.5">
              <p className="text-[10px] text-ink-faint uppercase tracking-wider">{m.label}</p>
              <p className={`text-[13.5px] font-bold mt-0.5 ${m.highlight || "text-ink"}`}>
                {m.value}
              </p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (result.scenario_type === "reduce_study_hours") {
    const curH = s3CurrentDailyHours ?? Number(dv.current_daily_hours ?? 2.0);
    const simH = s3SimulatedDailyHours ?? Number(dv.simulated_daily_hours ?? 3.0);
    const baselineScore = s3CurrentScore ?? Number(dv.baseline_score ?? 0);
    const scenarioScore = s3SimulatedScore ?? Number(dv.scenario_score ?? 0);
    const absDiff = s3AbsDiff ?? Number(dv.absolute_difference_pp ?? 0);
    const relDiff = s3RelDiff ?? Number(dv.relative_difference_pct ?? 0);

    const obsAvg = Number(dv.observed_avg_daily_hours ?? 0);
    const obsMin = Number(dv.observed_min_hours ?? 0);
    const obsMax = Number(dv.observed_max_hours ?? 0);
    const nAssessments = Number(dv.n_assessments ?? result.data_point_count ?? 0);
    const r2 = result.correlation_r_squared;

    return (
      <div className="space-y-3 mb-4">
        {/* KPI Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div className="rounded-lg bg-bg-soft p-2.5 border-l-2 border-red-500">
            <p className="text-[10px] text-ink-faint uppercase tracking-wider">
              Baseline Score ({curH.toFixed(2)}h/d)
            </p>
            <p className="text-[15px] font-bold text-ink mt-0.5">{baselineScore.toFixed(1)}%</p>
          </div>
          <div className="rounded-lg bg-bg-soft p-2.5 border-l-2 border-emerald-500">
            <p className="text-[10px] text-ink-faint uppercase tracking-wider">
              Scenario Score ({simH.toFixed(2)}h/d)
            </p>
            <p className="text-[15px] font-bold text-ink mt-0.5">{scenarioScore.toFixed(1)}%</p>
          </div>
          <div className="rounded-lg bg-bg-soft p-2.5">
            <p className="text-[10px] text-ink-faint uppercase tracking-wider">Absolute Difference</p>
            <p
              className={`text-[15px] font-bold mt-0.5 ${
                absDiff >= 0 ? "text-emerald-500" : "text-amber-500"
              }`}
            >
              {absDiff >= 0 ? "+" : ""}
              {absDiff.toFixed(1)} pp
            </p>
          </div>
          <div className="rounded-lg bg-bg-soft p-2.5">
            <p className="text-[10px] text-ink-faint uppercase tracking-wider">Relative Change</p>
            <p
              className={`text-[15px] font-bold mt-0.5 ${
                relDiff >= 0 ? "text-emerald-500" : "text-amber-500"
              }`}
            >
              {relDiff >= 0 ? "+" : ""}
              {relDiff.toFixed(1)}%
            </p>
          </div>
        </div>

        {/* Observed Data & Regression Meta */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[12px]">
          <div className="rounded-lg bg-bg-soft/70 p-2 border border-line/60">
            <span className="text-[10px] text-ink-faint uppercase block">Observed Avg Routine</span>
            <span className="font-semibold text-ink">{obsAvg.toFixed(2)} hrs/day</span>
          </div>
          <div className="rounded-lg bg-bg-soft/70 p-2 border border-line/60">
            <span className="text-[10px] text-ink-faint uppercase block">Observed Range</span>
            <span className="font-semibold text-ink">
              {obsMin.toFixed(1)}h – {obsMax.toFixed(1)}h
            </span>
          </div>
          <div className="rounded-lg bg-bg-soft/70 p-2 border border-line/60">
            <span className="text-[10px] text-ink-faint uppercase block">Assessments Evaluated</span>
            <span className="font-semibold text-ink">{nAssessments} exams</span>
          </div>
          <div className="rounded-lg bg-bg-soft/70 p-2 border border-line/60">
            <span className="text-[10px] text-ink-faint uppercase block">LOO R² Correlation</span>
            <span className="font-semibold text-ink">
              {r2 != null ? `${(r2 * 100).toFixed(1)}%` : "N/A"}
            </span>
          </div>
        </div>

        {/* Statistical correlation disclaimer */}
        <p className="text-[11px] text-ink-faint italic flex items-center gap-1.5">
          <I name="info" size={12} className="shrink-0 text-primary" />
          <span>
            Reflects an observed statistical correlation in your historical logs, not a guaranteed causal outcome.
          </span>
        </p>
      </div>
    );
  }

  if (result.scenario_type === "program_outcome") {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
        {[
          { label: "Program Duration", value: `${dv.program_duration_years} Years` },
          { label: "Total Cost", value: formatCurrency(dv.total_program_cost as number) },
          { label: "Best-Case Salary", value: formatCurrency(dv.best_case_salary as number) },
          { label: "Risk-Case Salary", value: formatCurrency(dv.risk_case_salary as number) },
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
  s3CurrentDailyHours,
  s3SimulatedDailyHours,
  s3CurrentScore,
  s3SimulatedScore,
}: {
  result: SimulationResponse;
  isDark: boolean;
  s3CurrentDailyHours?: number;
  s3SimulatedDailyHours?: number;
  s3CurrentScore?: number;
  s3SimulatedScore?: number;
}) {
  const lineLabels = result.lines.map((l) => l.label);
  const isCurrency =
    result.scenario_type === "increase_savings_rate" ||
    result.scenario_type === "buy_vs_rent" ||
    result.scenario_type === "program_outcome";

  // Build unified data array indexed by numeric x
  // D1 fix: sort by x numerically, NEVER localeCompare
  const pointsByX = new Map<number, { x: number; date: string; band?: [number, number]; [key: string]: any }>();

  for (const line of result.lines) {
    line.points.forEach((pt, idx) => {
      const xVal = pt.x != null ? pt.x : idx;
      if (!pointsByX.has(xVal)) {
        pointsByX.set(xVal, { x: xVal, date: pt.date });
      }
      pointsByX.get(xVal)![line.label] = pt.value;
    });
  }

  // CC3: The band fill is an Area between best and risk only, and only for S2 and S3
  const hasBand =
    (result.scenario_type === "fitness_plan" || result.scenario_type === "reduce_study_hours") &&
    lineLabels.includes("best_case") &&
    lineLabels.includes("risk_case");

  const data = Array.from(pointsByX.values())
    .sort((a, b) => a.x - b.x)
    .map((item) => {
      if (hasBand && item.best_case != null && item.risk_case != null) {
        return {
          ...item,
          band: [item.risk_case, item.best_case],
        };
      }
      return item;
    });

  const bandName =
    result.scenario_type === "fitness_plan"
      ? "80% variability band (assumes independent days)"
      : "80% confidence interval";

  const renderLines = () =>
    lineLabels.map((label) => {
      const role = resolveRole(label);
      const style = CHART_STYLES[role];
      const color = isDark ? style.color.dark : style.color.light;
      const displayName = getScenarioDisplayName(result.scenario_type, label);
      const isPrimary = role === "expected" || role === "baseline";

      return (
        <Line
          key={label}
          type="monotone"
          dataKey={label}
          stroke={color}
          strokeWidth={isPrimary ? 2.5 : 2}
          strokeDasharray={style.dash}
          dot={false}
          name={displayName}
        />
      );
    });

  const renderS3Annotations = () => {
    if (result.scenario_type !== "reduce_study_hours" || !result.derived_values) return null;

    const obsMin = Number(result.derived_values.observed_min_hours ?? 0);
    const obsMax = Number(result.derived_values.observed_max_hours ?? 8);

    return (
      <>
        {obsMin > 0 && (
          <ReferenceArea
            x1={0}
            x2={obsMin}
            fill={isDark ? "#334155" : "#E2E8F0"}
            fillOpacity={0.35}
            stroke={isDark ? "#64748B" : "#94A3B8"}
            strokeDasharray="3 3"
            label={{
              value: "Extrapolated",
              position: "insideTopLeft",
              fill: isDark ? "#94A3B8" : "#64748B",
              fontSize: 10,
            }}
          />
        )}
        {obsMax < 8 && (
          <ReferenceArea
            x1={obsMax}
            x2={8}
            fill={isDark ? "#334155" : "#E2E8F0"}
            fillOpacity={0.35}
            stroke={isDark ? "#64748B" : "#94A3B8"}
            strokeDasharray="3 3"
            label={{
              value: "Extrapolated",
              position: "insideTopRight",
              fill: isDark ? "#94A3B8" : "#64748B",
              fontSize: 10,
            }}
          />
        )}

        {s3CurrentDailyHours != null && s3CurrentScore != null && (
          <>
            <ReferenceLine
              segment={[
                { x: s3CurrentDailyHours, y: 0 },
                { x: s3CurrentDailyHours, y: s3CurrentScore },
              ]}
              stroke="#EF4444"
              strokeDasharray="3 3"
              strokeWidth={1.5}
            />
            <ReferenceDot
              x={s3CurrentDailyHours}
              y={s3CurrentScore}
              r={5}
              fill="#EF4444"
              stroke="#FFFFFF"
              strokeWidth={2}
            />
          </>
        )}

        {s3SimulatedDailyHours != null && s3SimulatedScore != null && (
          <>
            <ReferenceLine
              segment={[
                { x: s3SimulatedDailyHours, y: 0 },
                { x: s3SimulatedDailyHours, y: s3SimulatedScore },
              ]}
              stroke="#10B981"
              strokeDasharray="3 3"
              strokeWidth={1.5}
            />
            <ReferenceDot
              x={s3SimulatedDailyHours}
              y={s3SimulatedScore}
              r={5}
              fill="#10B981"
              stroke="#FFFFFF"
              strokeWidth={2}
            />
          </>
        )}
      </>
    );
  };

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
              dataKey="x"
              type="number"
              domain={["dataMin", "dataMax"]}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => formatScenarioXTick(result.scenario_type, v)}
              tick={{ fontSize: 10.5, fill: isDark ? "#CBD5E1" : "#4B5563", fontWeight: 500 }}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10.5, fill: isDark ? "#CBD5E1" : "#4B5563", fontWeight: 500 }}
              tickFormatter={(v: number) =>
                isCurrency
                  ? formatCompactINR(v)
                  : result.scenario_type === "reduce_study_hours"
                  ? `${v}%`
                  : v.toFixed(0)
              }
            />
            <Tooltip
              formatter={(val: number | string | Array<number>, name: string) => {
                if (Array.isArray(val)) return ["", ""];
                const num = Number(val);
                const displayVal = isCurrency
                  ? formatCurrency(num)
                  : result.scenario_type === "reduce_study_hours"
                  ? `${num.toFixed(1)}%`
                  : num.toFixed(1);
                return [displayVal, name];
              }}
              labelFormatter={(labelVal: number) => {
                const item = data.find((d) => d.x === labelVal);
                return `Date: ${item?.date || formatScenarioXTick(result.scenario_type, labelVal)}`;
              }}
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
            <Area
              type="monotone"
              dataKey="band"
              stroke="none"
              fill="url(#simBand)"
              fillOpacity={1}
              name={bandName}
              legendType="none"
            />
            {renderLines()}
            {renderS3Annotations()}
          </AreaChart>
        ) : (
          <LineChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
            <XAxis
              dataKey="x"
              type="number"
              domain={["dataMin", "dataMax"]}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => formatScenarioXTick(result.scenario_type, v)}
              tick={{ fontSize: 10.5, fill: isDark ? "#CBD5E1" : "#4B5563", fontWeight: 500 }}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10.5, fill: isDark ? "#CBD5E1" : "#4B5563", fontWeight: 500 }}
              tickFormatter={(v: number) =>
                isCurrency
                  ? formatCompactINR(v)
                  : result.scenario_type === "reduce_study_hours"
                  ? `${v}%`
                  : v.toFixed(0)
              }
            />
            <Tooltip
              formatter={(val: number | string | Array<number>, name: string) => {
                if (Array.isArray(val)) return ["", ""];
                const num = Number(val);
                const displayVal = isCurrency
                  ? formatCurrency(num)
                  : result.scenario_type === "reduce_study_hours"
                  ? `${num.toFixed(1)}%`
                  : num.toFixed(1);
                return [displayVal, name];
              }}
              labelFormatter={(labelVal: number) => {
                const item = data.find((d) => d.x === labelVal);
                return `Date: ${item?.date || formatScenarioXTick(result.scenario_type, labelVal)}`;
              }}
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
            {renderLines()}
            {renderS3Annotations()}
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

      {(status === "unavailable" || (status !== "pending" && status !== "ready")) && (
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
