import {
  useEffect,
  useSyncExternalStore,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { getDataVersion, subscribeData } from "../lib/store";
import { I } from "./icons";

/** Re-render hook: bumps whenever any repository writes. */
export function useDataVersion(): number {
  return useSyncExternalStore(subscribeData, getDataVersion);
}

/* ---------------- toasts ---------------- */

export interface ToastMsg {
  id: number;
  text: string;
  kind: "ok" | "err" | "info";
}

let toastList: ToastMsg[] = [];
const toastListeners = new Set<() => void>();
let toastSeq = 1;

export function toast(text: string, kind: ToastMsg["kind"] = "ok"): void {
  const msg: ToastMsg = { id: toastSeq++, text, kind };
  toastList = [...toastList.slice(-3), msg];
  toastListeners.forEach((fn) => fn());
  setTimeout(() => {
    toastList = toastList.filter((t) => t.id !== msg.id);
    toastListeners.forEach((fn) => fn());
  }, 3800);
}

function subscribeToasts(fn: () => void): () => void {
  toastListeners.add(fn);
  return () => {
    toastListeners.delete(fn);
  };
}

export function ToastHost() {
  const list = useSyncExternalStore(subscribeToasts, () => toastList);
  return (
    <div className="fixed bottom-5 right-5 z-[80] flex flex-col gap-2 items-end">
      {list.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`anim-toast flex items-center gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm font-medium shadow-lift max-w-[340px] ${
            t.kind === "ok"
              ? "bg-pine text-mint border-pine-deep"
              : t.kind === "err"
                ? "bg-coral text-[#fdf3f0] border-[#a03227]"
                : "bg-panel text-ink border-line-strong"
          }`}
        >
          <I name={t.kind === "ok" ? "check" : t.kind === "err" ? "alert" : "info"} size={16} />
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------------- buttons ---------------- */

type BtnVariant = "primary" | "subtle" | "ghost" | "danger" | "amber";

export function Btn({
  variant = "primary",
  size = "md",
  loading = false,
  className = "",
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md"; loading?: boolean }) {
  const base =
    "inline-flex items-center justify-center gap-1.5 font-semibold rounded-lg transition-all duration-150 active:translate-y-px disabled:opacity-50 disabled:pointer-events-none focus-ring";
  const sizes = size === "sm" ? "text-[13px] px-2.5 py-1.5" : "text-sm px-4 py-2";
  const variants: Record<BtnVariant, string> = {
    primary: "bg-pine text-mint hover:bg-pine-deep shadow-lift hover:-translate-y-px",
    subtle: "bg-panel text-ink border border-line-strong hover:border-pine/40 hover:bg-card",
    ghost: "text-ink-soft hover:text-ink hover:bg-pine/8",
    danger: "bg-coral text-[#fdf3f0] hover:bg-[#a83a2e] shadow-lift",
    amber: "bg-amber-bright text-pine-ink hover:bg-[#d2952a] shadow-lift hover:-translate-y-px",
  };
  return (
    <button className={`${base} ${sizes} ${variants[variant]} ${className}`} disabled={disabled || loading} {...rest}>
      {loading && (
        <span className="w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden />
      )}
      {children}
    </button>
  );
}

/* ---------------- form primitives ---------------- */

export function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string | null;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="flex items-baseline justify-between mb-1.5">
        <span className="text-[12.5px] font-semibold uppercase tracking-[0.08em] text-ink-soft">{label}</span>
        {hint && <span className="text-[11.5px] text-ink-faint font-mono">{hint}</span>}
      </span>
      {children}
      {error && (
        <span className="mt-1.5 flex items-center gap-1 text-[12.5px] font-medium text-coral">
          <I name="alert" size={13} />
          {error}
        </span>
      )}
    </label>
  );
}

export function Input({
  invalid,
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      className={`w-full rounded-lg border bg-panel px-3 py-2 text-[15px] text-ink placeholder:text-ink-faint focus-ring ${
        invalid ? "border-coral" : "border-line-strong"
      } ${className}`}
      {...rest}
    />
  );
}

export function Select({
  invalid,
  className = "",
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <select
      className={`w-full rounded-lg border bg-panel px-3 py-2 text-[15px] text-ink focus-ring appearance-none bg-no-repeat bg-[right_10px_center] ${
        invalid ? "border-coral" : "border-line-strong"
      } ${className}`}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%2352665b' stroke-width='2' stroke-linecap='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
      }}
      {...rest}
    >
      {children}
    </select>
  );
}

export function Segmented({
  options,
  value,
  onChange,
  accent,
}: {
  options: Array<{ value: string; label: string }>;
  value: string;
  onChange: (v: string) => void;
  accent?: string;
}) {
  return (
    <div className="inline-flex rounded-lg border border-line-strong bg-card p-0.5 gap-0.5">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className={`px-3.5 py-1.5 rounded-md text-[13.5px] font-semibold transition-all duration-150 ${
              active ? "text-mint shadow-lift" : "text-ink-soft hover:text-ink"
            }`}
            style={active ? { background: accent ?? "var(--color-pine)" } : undefined}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ---------------- display primitives ---------------- */

export function Chip({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: "neutral" | "ok" | "warn" | "breach" | "pine" | "custom";
  children: ReactNode;
  className?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "bg-card text-ink-soft border-line-strong",
    ok: "bg-ok-soft text-ok border-ok/25",
    warn: "bg-warn-soft text-amber border-amber/30",
    breach: "bg-breach-soft text-coral border-coral/30",
    pine: "bg-pine text-mint border-pine-deep",
    custom: "border-transparent",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[12px] font-semibold whitespace-nowrap ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function Bar({
  pct,
  accent,
  height = 8,
  marker,
}: {
  pct: number;
  accent: string;
  height?: number;
  marker?: number;
}) {
  const clamped = Math.max(0, Math.min(100, pct));
  const over = pct > 100;
  return (
    <div className="relative w-full rounded-full bg-pine/10 overflow-hidden" style={{ height }}>
      <div
        className="absolute inset-y-0 left-0 rounded-full anim-bar transition-[width] duration-700"
        style={{ width: `${clamped}%`, background: over ? "var(--color-coral)" : accent }}
      />
      {marker != null && (
        <div className="absolute inset-y-0 w-[2px] bg-ink/40" style={{ left: `${Math.min(99, marker)}%` }} title="pace marker" />
      )}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon: string;
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="anim-rise flex flex-col items-center text-center py-14 px-6">
      <div className="w-14 h-14 rounded-2xl bg-pine/8 border border-pine/15 flex items-center justify-center text-pine mb-4">
        <I name={icon} size={26} sw={1.5} />
      </div>
      <h3 className="font-display text-lg font-semibold text-ink">{title}</h3>
      <p className="mt-1.5 text-sm text-ink-soft max-w-[380px] leading-relaxed">{body}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/* ---------------- modal ---------------- */

export function Modal({
  open,
  onClose,
  title,
  children,
  width = "max-w-lg",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  width?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center p-4">
      <button aria-label="Close" className="absolute inset-0 bg-pine-ink/45 backdrop-blur-[2px] cursor-default" onClick={onClose} />
      <div className={`anim-pop relative w-full ${width} rounded-xl border border-line bg-panel shadow-pop`}>
        <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-line">
          <h3 className="font-display text-[17px] font-semibold text-ink">{title}</h3>
          <button onClick={onClose} className="p-1.5 rounded-md text-ink-faint hover:text-ink hover:bg-pine/8 transition-colors focus-ring">
            <I name="x" size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

/* ---------------- misc ---------------- */

export function fmtMoney(n: number, currency: string): string {
  const sign = n < 0 ? "−" : "";
  return `${sign}${currency}${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}

export function fmtDate(iso: string): string {
  const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}
