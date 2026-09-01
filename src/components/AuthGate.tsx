import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../lib/auth";
import { DEMO_EMAIL, DEMO_PASSWORD } from "../lib/seed";
import { checkPassword, validateEmail } from "../lib/validation";
import { useAuth } from "../state/AuthContext";
import { I, LogoMark } from "./icons";
import { Btn, Field, Input, toast } from "./ui";

const LOG_LINES: Array<[string, string, string, string]> = [
  ["07:12", "fitness", "5K run · 42 min", "baseline ok"],
  ["08:03", "habits", "Read 20 pages", "completed"],
  ["09:41", "money", "Groceries −$23.10", "within cap"],
  ["11:26", "study", "Algorithms · 1.75 h", "pace +12%"],
  ["13:05", "money", "Campus lunch −$8.40", "within cap"],
  ["16:44", "grades", "Quiz 3 · 17/20", "recorded"],
  ["19:20", "savings", "Vault transfer +$60", "on pace"],
  ["21:58", "goals", "Emergency fund → $830", "55% reached"],
  ["22:31", "habits", "Lights out 23:30", "pending"],
  ["23:02", "money", "Cap usage 81%", "monitor"],
];

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="font-mono text-[13px] text-mint/80 tabular tracking-wider">
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
        toast("Signed in — console live.", "ok");
      } else {
        await register(email, password);
        toast("Account created. Set your baselines in Profile.", "ok");
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
    <div className="min-h-screen flex bg-mist">
      {/* -------- left: live console -------- */}
      <aside className="hidden lg:flex w-[52%] xl:w-[55%] flex-col bg-pine-deep bg-console text-mint relative overflow-hidden">
        <div className="absolute inset-0 bg-dark-grid opacity-60 pointer-events-none" />
        <div className="relative flex items-center justify-between px-10 pt-8">
          <div className="flex items-center gap-3">
            <LogoMark size={38} className="text-mint" />
            <div>
              <div className="font-display font-bold text-[19px] leading-none tracking-tight">RiskLens</div>
              <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mint/50 mt-1">
                personal risk · compliance intel
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2.5 rounded-full border border-mint/15 bg-pine-ink/40 px-3.5 py-1.5">
            <span className="relative flex w-2 h-2">
              <span className="absolute inline-flex w-full h-full rounded-full bg-amber-bright" style={{ animation: "rl-ping 2s cubic-bezier(0,0,0.2,1) infinite" }} />
              <span className="relative inline-flex w-2 h-2 rounded-full bg-amber-bright" />
            </span>
            <Clock />
          </div>
        </div>

        <div className="relative flex-1 flex flex-col justify-center px-10 xl:px-16 py-10">
          <p className="font-mono text-[12px] uppercase tracking-[0.24em] text-amber-bright mb-4">milestone 01 · telemetry online</p>
          <h1 className="font-display font-bold text-[44px] xl:text-[54px] leading-[1.02] tracking-tight max-w-[560px]">
            See the risk<br />
            before it <span className="text-amber-bright">lands.</span>
          </h1>
          <p className="mt-5 max-w-[440px] text-[15.5px] leading-relaxed text-mint/70">
            RiskLens watches the signals you already generate — money, study hours, training, habits —
            and checks them against the limits <em className="not-italic text-mint font-semibold">you</em> set for yourself.
          </p>

          {/* live event ticker */}
          <div className="mt-9 max-w-[520px] rounded-xl border border-mint/12 bg-pine-ink/50 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 border-b border-mint/10">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-mint/50">live event log</span>
              <span className="font-mono text-[10.5px] text-mint/40">demo feed</span>
            </div>
            <div className="h-[148px] overflow-hidden relative">
              <div style={{ animation: "rl-ticker 22s linear infinite" }}>
                {[...LOG_LINES, ...LOG_LINES].map(([t, src, msg, status], i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-[5.5px] font-mono text-[12px] border-b border-mint/5">
                    <span className="text-mint/40 tabular">{t}</span>
                    <span className="text-amber-bright/90 w-[58px] shrink-0">{src}</span>
                    <span className="text-mint/85 truncate flex-1">{msg}</span>
                    <span className={`text-[10.5px] uppercase tracking-wider ${status.includes("monitor") || status === "pending" ? "text-amber-bright/80" : "text-[#7fc79b]"}`}>
                      {status}
                    </span>
                  </div>
                ))}
              </div>
              <div className="absolute inset-x-0 top-0 h-6 bg-gradient-to-b from-pine-ink/80 to-transparent pointer-events-none" />
              <div className="absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-pine-ink/80 to-transparent pointer-events-none" />
            </div>
          </div>
        </div>

        <div className="relative px-10 pb-8 flex items-center gap-5 font-mono text-[11px] text-mint/45">
          <span className="flex items-center gap-1.5"><I name="shield" size={13} /> salted PBKDF2 hashing</span>
          <span className="flex items-center gap-1.5"><I name="key" size={13} /> rotating refresh tokens</span>
          <span className="flex items-center gap-1.5"><I name="user" size={13} /> per-user isolation</span>
        </div>
      </aside>

      {/* -------- right: auth form -------- */}
      <main className="flex-1 flex flex-col bg-blueprint">
        <div className="lg:hidden flex items-center gap-2.5 px-6 pt-6">
          <span className="text-pine"><LogoMark size={30} /></span>
          <span className="font-display font-bold text-[17px] text-ink">RiskLens</span>
        </div>

        <div className="flex-1 flex items-center justify-center px-6 py-10">
          <div className="w-full max-w-[420px]">
            <div className="anim-rise">
              <p className="font-mono text-[11.5px] uppercase tracking-[0.22em] text-moss mb-2.5">secure access</p>
              <h2 className="font-display font-bold text-[30px] leading-tight text-ink tracking-tight">
                {mode === "login" ? "Open your console." : "Create your console."}
              </h2>
              <p className="mt-2 text-[14.5px] text-ink-soft">
                {mode === "login"
                  ? "Pick up your signals where you left off."
                  : "One profile. Seven data sources. Your baselines, your rules."}
              </p>
            </div>

            <div className="anim-rise mt-7 flex rounded-lg border border-line-strong bg-card p-0.5 gap-0.5" style={{ animationDelay: "60ms" }}>
              {(["login", "register"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => switchMode(m)}
                  className={`flex-1 py-2 rounded-md text-[13.5px] font-semibold transition-all ${
                    mode === m ? "bg-pine text-mint shadow-lift" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {m === "login" ? "Sign in" : "Create account"}
                </button>
              ))}
            </div>

            {banner && (
              <div className="anim-pop mt-4 flex items-start gap-2 rounded-lg border border-coral/30 bg-coral-soft px-3.5 py-2.5 text-[13.5px] font-medium text-coral">
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
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink transition-colors"
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
                                ? "var(--color-coral)"
                                : pwCheck.score === 2
                                  ? "var(--color-amber-bright)"
                                  : "var(--color-moss-bright)"
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

            <div className="mt-6 rounded-lg border border-dashed border-moss/35 bg-mint/40 px-4 py-3.5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[13px] font-semibold text-pine">Demo console</p>
                  <p className="font-mono text-[11.5px] text-ink-soft mt-0.5">
                    {DEMO_EMAIL} · 60 days of seeded history
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
              Passwords are salted &amp; hashed (PBKDF2-SHA256). Sessions use short-lived access tokens with
              rotating 7-day refresh tokens.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
