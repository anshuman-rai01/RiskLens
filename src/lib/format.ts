/**
 * Compact formatting utilities for the RiskLens frontend.
 */

/**
 * Format a monetary amount compactly using Indian units (K, L, Cr) for chart axes:
 * e.g. 500 -> "₹500", 5000 -> "₹5K", 150000 -> "₹1.5L", 10000000 -> "₹1Cr".
 */
export function formatCompactINR(amount: number): string {
  if (!Number.isFinite(amount)) return "₹0";
  const isNegative = amount < 0;
  const abs = Math.abs(amount);

  let formatted = "";
  if (abs >= 1_00_00_000) {
    const cr = abs / 1_00_00_000;
    formatted = `${parseFloat(cr.toFixed(2))}Cr`;
  } else if (abs >= 1_00_000) {
    const l = abs / 1_00_000;
    formatted = `${parseFloat(l.toFixed(1))}L`;
  } else if (abs >= 1_000) {
    const k = abs / 1_000;
    formatted = `${parseFloat(k.toFixed(1))}K`;
  } else {
    formatted = `${Math.round(abs)}`;
  }

  return isNegative ? `-₹${formatted}` : `₹${formatted}`;
}
