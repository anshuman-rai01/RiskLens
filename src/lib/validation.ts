/**
 * Pure validation rules — reused by the auth service and entry repositories here,
 * and designed to translate 1:1 into Pydantic schemas on the FastAPI port.
 */

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function validateEmail(email: string): string | null {
  const v = email.trim();
  if (!v) return "Email is required.";
  if (v.length > 254) return "Email is too long.";
  if (!EMAIL_RE.test(v)) return "That doesn't look like a valid email address.";
  return null;
}

export interface PasswordCheck {
  ok: boolean;
  message: string | null;
  score: 0 | 1 | 2 | 3 | 4;
}

export function checkPassword(pw: string): PasswordCheck {
  if (!pw) return { ok: false, message: "Password is required.", score: 0 };
  if (pw.length < 8) return { ok: false, message: "Use at least 8 characters.", score: 1 };
  if (!/[a-zA-Z]/.test(pw) || !/\d/.test(pw))
    return { ok: false, message: "Mix letters with at least one number.", score: 1 };

  let score = 2;
  if (pw.length >= 12) score += 1;
  if (pw.length >= 12 && /[^a-zA-Z0-9]/.test(pw)) score += 1;
  const clamped = Math.min(4, Math.max(0, score)) as 0 | 1 | 2 | 3 | 4;
  if (pw.length > 72) return { ok: false, message: "Keep it under 72 characters.", score: clamped };
  return { ok: true, message: null, score: clamped };
}

export function isPositiveNum(n: unknown): boolean {
  return typeof n === "number" && Number.isFinite(n) && n > 0;
}

export function isNonNegativeNum(n: unknown): boolean {
  return typeof n === "number" && Number.isFinite(n) && n >= 0;
}

export const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function isValidDate(s: string): boolean {
  if (!DATE_RE.test(s)) return false;
  const d = new Date(s + "T12:00:00");
  return !Number.isNaN(d.getTime());
}

export function notFarFuture(s: string, maxYears = 10): boolean {
  const d = new Date(s + "T12:00:00");
  const limit = new Date();
  limit.setFullYear(limit.getFullYear() + maxYears);
  return d.getTime() <= limit.getTime();
}

export function textLen(s: string, max: number): boolean {
  return s.length <= max;
}
