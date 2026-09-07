import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../lib/auth";
import { DEMO_EMAIL, DEMO_PASSWORD } from "../lib/seed";
import { checkPassword, validateEmail } from "../lib/validation";
import { useAuth } from "../state/AuthContext";
import { I, LogoMark } from "./icons";
import { Btn, Field, Input, toast } from "./ui";

const LOG_LINES: Array<[string, string, string, string]> = [
  ["07:12", "activity", "Morning run · 42 min", "streak +1"],
  ["08:03", "habits", "Meditate 10 min", "completed"],
  ["09:41", "focus", "Deep work session", "90 min"],
  ["11:26", "study", "ML Algorithms · 1.75 h", "pace +12%"],
  ["13:05", "tasks", "Project A milestone", "completed"],
  ["16:44", "goals", "Read 30 pages", "on track"],
  ["19:20", "habits", "No sugar today", "5 day streak"],
  ["21:58", "insights", "Productivity score: 8.2", "↑ 12%"],
  ["22:31", "habits", "Journal entry", "pending"],
  ["23:02", "summary", "Weekly goal: 85%", "monitor"],
];

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="font-mono text-[13px] text-ink-faint tabular tracking-wider">
      {now.toLocaleTimeString(undefined, { hour12: false })}
    </span>
  );
}

export function AuthGate() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const pwCheck = useMemo(() => checkPassword(password), [password]);

  const switchMode = (m: "login" | "register") => {
    setMode(m);
    setErrors({});
    setBanner(null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const next: { email?: string; password?: string } = {};
    const emailErr = validateEmail(email);
    if (emailErr) next.email = emailErr;
    if (mode === "register") {
      if (!pwCheck.ok) next.password = pwCheck.message ?? "Password too weak.";
    } else if (!password) {
      next.password = "Password is required.";
    }
    setErrors(next);
    setBanner(null);
    if (next.email || next.password) return;

    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
        toast("Welcome back! Console is live.", "ok");
      } else {
        await register(email, password);
        toast("Account created. Start tracking your progress!", "ok");
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.field === "email") setErrors({ email: err.message });
        else if (err.field === "password") setErrors({ password: err.message });
        else setBanner(err.message);
      } else {
        setBanner("Something went wrong. Try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-bg">
      {/* Left: branding panel */}
      <aside className="hidden lg:flex w-[52%] xl:w-[55%] flex-col bg-card border-r border-line relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-primary-soft opacity-50" />
        <div className="absolute top-0 right-0 w-96 h-96 rounded-full bg-primary/10 -translate-y-48 translate-x-48" />
        <div className="absolute bottom-0 left-0 w-80 h-80 rounded-full bg-primary/10 translate-y-40 -translate-x-40" />

        <div className="relative flex items-center justify-between px-10 pt-8">
          <div className="flex items-center gap-3">
            <LogoMark size={38} />
            <div>
              <div className="font-display font-bold text-[19px] leading-none tracking-tight text-ink">Productivity Engine</div>
              <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-ink-faint mt-1">
                Track · Analyze · Improve
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2.5 rounded-full border border-line bg-bg-soft px-3.5 py-1.5">
            <span className="relative flex w-2 h-2">
              <span className="absolute inline-flex w-full h-full rounded-full bg-primary" style={{ animation: "pl-ping 2s cubic-bezier(0,0,0.2,1) infinite" }} />
              <span className="relative inline-flex w-2 h-2 rounded-full bg-primary" />
            </span>
            <Clock />
          </div>
        </div>

        <div className="relative flex-1 flex flex-col justify-center px-10 xl:px-16 py-10">
          <p className="font-mono text-[12px] uppercase tracking-[0.24em] text-primary mb-4">Your personal analytics</p>
          <h1 className="font-display font-bold text-[44px] xl:text-[54px] leading-[1.02] tracking-tight max-w-[560px] text-ink">
            Track. Analyze.<br />
            <span className="text-gradient-primary">Improve.</span> Every day.
          </h1>
          <p className="mt-5 max-w-[440px] text-[15.5px] leading-relaxed text-ink-soft">
            Monitor your habits, focus sessions, and productivity patterns. Get actionable insights to build better routines and achieve your goals.
          </p>

          {/* Activity ticker */}
          <div className="mt-9 max-w-[520px] rounded-xl border border-line bg-card overflow-hidden shadow-sm">
            <div className="flex items-center justify-between px-4 py-2 border-b border-line">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-faint">Live activity</span>
              <span className="font-mono text-[10.5px] text-ink-muted">demo feed</span>
            </div>
            <div className="h-[148px] overflow-hidden relative">
              <div style={{ animation: "pl-ticker 22s linear infinite" }}>
                {[...LOG_LINES, ...LOG_LINES].map(([t, src, msg, status], i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-[5.5px] font-mono text-[12px] border-b border-line">
                    <span className="text-ink-muted tabular">{t}</span>
                    <span className="text-primary w-[58px] shrink-0">{src}</span>
                    <span className="text-ink-soft truncate flex-1">{msg}</span>
                    <span className={`text-[10.5px] uppercase tracking-wider ${status.includes("monitor") || status === "pending" ? "text-warn" : "text-ok"}`}>
                      {status}
                    </span>
                  </div>
                ))}
              </div>
              <div className="absolute inset-x-0 top-0 h-6 bg-gradient-to-b from-card to-transparent pointer-events-none" />
              <div className="absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-card to-transparent pointer-events-none" />
            </div>
          </div>
        </div>

        <div className="relative px-10 pb-8 flex items-center gap-5 font-mono text-[11px] text-ink-faint">
          <span className="flex items-center gap-1.5"><I name="shield" size={13} /> Secure authentication</span>
          <span className="flex items-center gap-1.5"><I name="zap" size={13} /> Real-time insights</span>
          <span className="flex items-center gap-1.5"><I name="user" size={13} /> Private & personal</span>
        </div>
      </aside>

      {/* Right: auth form */}
      <main className="flex-1 flex flex-col">
        <div className="lg:hidden flex items-center gap-2.5 px-6 pt-6">
          <LogoMark size={30} />
          <span className="font-display font-bold text-[17px] text-ink">Productivity Engine</span>
        </div>

        <div className="flex-1 flex items-center justify-center px-6 py-10">
          <div className="w-full max-w-[420px]">
            <div className="anim-rise">
              <p className="font-mono text-[11.5px] uppercase tracking-[0.22em] text-primary mb-2.5">Secure access</p>
              <h2 className="font-display font-bold text-[30px] leading-tight text-ink tracking-tight">
                {mode === "login" ? "Welcome back." : "Start your journey."}
              </h2>
              <p className="mt-2 text-[14.5px] text-ink-soft">
                {mode === "login"
                  ? "Pick up your progress where you left off."
                  : "Track habits, focus sessions, and goals in one place."}
              </p>
            </div>

            <div className="anim-rise mt-7 flex rounded-lg border border-line bg-bg-soft p-0.5 gap-0.5" style={{ animationDelay: "60ms" }}>
              {(["login", "register"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => switchMode(m)}
                  className={`flex-1 py-2 rounded-md text-[13.5px] font-semibold transition-all ${
                    mode === m ? "bg-gradient-primary text-white shadow-md" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {m === "login" ? "Sign in" : "Create account"}
                </button>
              ))}
            </div>

            {banner && (
              <div className="anim-pop mt-4 flex items-start gap-2 rounded-lg border border-danger/30 bg-danger-soft px-3.5 py-2.5 text-[13.5px] font-medium text-danger">
                <I name="alert" size={15} className="mt-0.5 shrink-0" />
                {banner}
              </div>
            )}

            <form onSubmit={submit} className="mt-5 space-y-4" noValidate>
              <Field label="Email" error={errors.email}>
                <Input
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  invalid={!!errors.email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field
                label="Password"
                error={errors.password}
                hint={mode === "register" ? "min 8 chars · letter + number" : undefined}
              >
                <div className="relative">
                  <Input
                    type={showPw ? "text" : "password"}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    placeholder="••••••••"
                    value={password}
                    invalid={!!errors.password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((s) => !s)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink transition-colors"
                    aria-label={showPw ? "Hide password" : "Show password"}
                  >
                    <I name={showPw ? "eyeoff" : "eye"} size={16} />
                  </button>
                </div>
              </Field>

              {mode === "register" && password.length > 0 && (
                <div className="anim-pop">
                  <div className="flex gap-1.5">
                    {[1, 2, 3, 4].map((seg) => (
                      <div
                        key={seg}
                        className="h-1.5 flex-1 rounded-full transition-colors duration-300"
                        style={{
                          background:
                            pwCheck.score >= seg
                              ? pwCheck.score <= 1
                                ? "var(--color-danger)"
                                : pwCheck.score === 2
                                  ? "var(--color-warn)"
                                  : "var(--color-ok)"
                              : "var(--color-line)",
                        }}
                      />
                    ))}
                  </div>
                  <p className="mt-1.5 text-[12px] font-mono text-ink-faint">
                    strength: {["—", "weak", "fair", "good", "strong"][pwCheck.score]}
                  </p>
                </div>
              )}

              <Btn type="submit" loading={loading} className="w-full py-2.5">
                {mode === "login" ? "Sign in" : "Create account"}
                <I name="arrow" size={15} />
              </Btn>
            </form>

            <div className="mt-6 rounded-lg border border-dashed border-primary/35 bg-primary-soft px-4 py-3.5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[13px] font-semibold text-primary">Demo account</p>
                  <p className="font-mono text-[11.5px] text-ink-soft mt-0.5">
                    {DEMO_EMAIL} · Sample data included
                  </p>
                </div>
                <Btn
                  variant="subtle"
                  size="sm"
                  onClick={() => {
                    setEmail(DEMO_EMAIL);
                    setPassword(DEMO_PASSWORD);
                    setMode("login");
                    setErrors({});
                    setBanner(null);
                    toast("Demo credentials filled — hit Sign in.", "info");
                  }}
                >
                  Fill
                </Btn>
              </div>
            </div>

            <p className="mt-6 text-center text-[12px] text-ink-faint leading-relaxed max-w-[360px] mx-auto">
              Your data is private and secure. Passwords are salted &amp; hashed. Sessions use rotating tokens.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
