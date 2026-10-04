import { describe, it, expect } from "vitest";
import {
  projectSavings,
  projectFitness,
  calculateMortgageEMI,
  interpolateCurve,
  formatCompactINR,
  formatScenarioXTick,
  resolveRole,
  getScenarioDisplayName,
  SIM_BOUNDS,
  SIM_DEFAULTS,
} from "./simulationMath";

describe("Scenario 1: projectSavings (Golden Numbers)", () => {
  it("matches acceptance golden numbers at N=12 and N=0", () => {
    // Golden: base=100000, avg_income=50000, current_rate=0.10, target=0.25, N=12
    // gives 160,000 and 250,000
    const res = projectSavings(100000, 50000, 0.10, 0.25, 12);
    expect(res.currentPath).toHaveLength(13);
    expect(res.expectedPath).toHaveLength(13);

    // N = 0 is exactly base_savings on both lines
    expect(res.currentPath[0].x).toBe(0);
    expect(res.currentPath[0].value).toBe(100000);
    expect(res.expectedPath[0].x).toBe(0);
    expect(res.expectedPath[0].value).toBe(100000);

    // N = 12 matches golden numbers
    expect(res.currentPath[12].x).toBe(12);
    expect(res.currentPath[12].value).toBe(160000);
    expect(res.expectedPath[12].x).toBe(12);
    expect(res.expectedPath[12].value).toBe(250000);
  });
});

describe("Scenario 2: projectFitness (Golden Numbers)", () => {
  it("matches acceptance golden numbers at D=90 and D=0", () => {
    // Golden: historical_daily_avg=20, sigma=10, T=30 (target_weekly_minutes=210), D=90
    // gives baseline 1800, expected 2700, best 2821.6, risk 2578.4
    const res = projectFitness(20, 10, 210, 90);
    expect(res.baseline).toHaveLength(91);

    // D = 0 is 0 on all four lines
    expect(res.baseline[0].value).toBe(0);
    expect(res.expected[0].value).toBe(0);
    expect(res.best[0].value).toBe(0);
    expect(res.risk[0].value).toBe(0);

    // D = 90
    expect(res.baseline[90].value).toBe(1800);
    expect(res.expected[90].value).toBe(2700);
    expect(res.best[90].value).toBeCloseTo(2821.6, 1);
    expect(res.risk[90].value).toBeCloseTo(2578.4, 1);
  });

  it("yields zero band width when sigma is 0", () => {
    const res = projectFitness(20, 0, 210, 30);
    for (let d = 0; d <= 30; d++) {
      expect(res.best[d].value).toBe(res.expected[d].value);
      expect(res.risk[d].value).toBe(res.expected[d].value);
    }
  });

  it("ensures risk never drops below 0", () => {
    // Very high sigma that would make expected - spread negative
    const res = projectFitness(10, 100, 70, 90); // T = 10, spread >> 900
    for (const pt of res.risk) {
      expect(pt.value).toBeGreaterThanOrEqual(0);
    }
  });
});

describe("Scenario 4: calculateMortgageEMI (Golden Numbers)", () => {
  it("matches acceptance golden EMI calculation", () => {
    // Golden EMI: ₹50,00,000 price, 20% down (₹40,00,000 loan), 8.5%, 20 y gives 34,712.93
    const principal = 5000000 * 0.8;
    const emi = calculateMortgageEMI(principal, 8.5, 20);
    expect(emi).toBe(34712.93);
  });

  it("handles 0% mortgage rate without divide-by-zero", () => {
    const principal = 1200000;
    const emi = calculateMortgageEMI(principal, 0, 10);
    expect(emi).toBe(10000);
  });
});

describe("Scenario 3: interpolateCurve", () => {
  it("interpolates values smoothly and clamps to [0, 100]", () => {
    const grid = [
      { x: 0, value: 50 },
      { x: 2, value: 70 },
      { x: 4, value: 90 },
      { x: 6, value: 95 },
      { x: 8, value: 98 },
    ];

    expect(interpolateCurve(grid, 0)).toBe(50);
    expect(interpolateCurve(grid, 1)).toBe(60);
    expect(interpolateCurve(grid, 2)).toBe(70);
    expect(interpolateCurve(grid, 3)).toBe(80);
    expect(interpolateCurve(grid, 4)).toBe(90);

    // Clamps at limits
    expect(interpolateCurve(grid, -1)).toBe(50);
    expect(interpolateCurve(grid, 10)).toBe(98);
  });
});

describe("Formatters: formatCompactINR", () => {
  it("formats currency correctly into INR compact strings", () => {
    expect(formatCompactINR(0)).toBe("₹0");
    expect(formatCompactINR(500)).toBe("₹500");
    expect(formatCompactINR(15000)).toBe("₹15K");
    expect(formatCompactINR(150000)).toBe("₹1.5L");
    expect(formatCompactINR(5000000)).toBe("₹50L");
    expect(formatCompactINR(12000000)).toBe("₹1.2Cr");
    expect(formatCompactINR(-50000)).toBe("-₹50K");
  });

  it("formats X axis ticks per scenario", () => {
    expect(formatScenarioXTick("increase_savings_rate", 12)).toBe("M12");
    expect(formatScenarioXTick("fitness_plan", 30)).toBe("Day 30");
    expect(formatScenarioXTick("reduce_study_hours", 4)).toBe("4h");
    expect(formatScenarioXTick("buy_vs_rent", 5)).toBe("Yr 5");
    expect(formatScenarioXTick("program_outcome", 10)).toBe("Year 10");
  });
});

describe("Role and Style Mapping (CC3)", () => {
  it("resolves roles and handles all aliases including Buy and Rent", () => {
    expect(resolveRole("current_path_expected")).toBe("baseline");
    expect(resolveRole("current_baseline")).toBe("baseline");
    expect(resolveRole("without_program")).toBe("baseline");
    expect(resolveRole("expected_case")).toBe("expected");
    expect(resolveRole("best_case")).toBe("best");
    expect(resolveRole("risk_case")).toBe("risk");
    expect(resolveRole("Buy")).toBe("buy");
    expect(resolveRole("Rent")).toBe("rent");
  });

  it("returns scenario-specific display names", () => {
    expect(getScenarioDisplayName("increase_savings_rate", "current_path_expected")).toBe("Current Trajectory");
    expect(getScenarioDisplayName("program_outcome", "without_program")).toBe("Current Path");
    expect(getScenarioDisplayName("buy_vs_rent", "Buy")).toBe("Buy (Property Equity & Portfolio)");
    expect(getScenarioDisplayName("buy_vs_rent", "Rent")).toBe("Rent (Invested Portfolio)");
  });
});

describe("Bounds and Defaults (CC7, CC8)", () => {
  it("exports bounds and defaults objects", () => {
    expect(SIM_BOUNDS.increase_savings_rate.target_rate.max).toBe(100);
    expect(SIM_DEFAULTS.increase_savings_rate.target_rate).toBe(20);
    expect(SIM_DEFAULTS.program_outcome.current_annual_salary).toBe("");
  });
});
