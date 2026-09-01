/**
 * Centralized currency system — the single source of truth for all monetary
 * representation in RiskLens.
 *
 * Application currency: Indian Rupee (INR / ₹), formatted with Indian digit
 * grouping (en-IN): ₹500 · ₹1,000 · ₹10,000 · ₹1,00,000 · ₹10,00,000.
 *
 * Amounts are stored as plain numbers without currency metadata, so display
 * must ALWAYS go through this module — never hand-assemble `${symbol}${n}`.
 */

export const CURRENCY_CODE = "INR";
export const CURRENCY_SYMBOL = "₹";
export const CURRENCY_NAME = "Indian Rupee";
export const CURRENCY_LOCALE = "en-IN";

const currencyFmt = new Intl.NumberFormat(CURRENCY_LOCALE, {
  style: "currency",
  currency: CURRENCY_CODE,
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

const numberFmt = new Intl.NumberFormat(CURRENCY_LOCALE, {
  maximumFractionDigits: 2,
});

/** Format a monetary amount: 125000 → "₹1,25,000". Negatives use a typographic minus. */
export function formatCurrency(amount: number): string {
  const n = Number.isFinite(amount) ? amount : 0;
  return currencyFmt.format(n).replace(/^-/, "−");
}

/** Plain Indian-grouped number for goal-style values that carry their own unit. */
export function formatINR(amount: number): string {
  const n = Number.isFinite(amount) ? amount : 0;
  return numberFmt.format(n);
}
