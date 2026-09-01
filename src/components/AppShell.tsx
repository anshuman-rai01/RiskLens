import { useEffect, useRef, useState, type ReactNode } from "react";
import { CATEGORY_LIST } from "../lib/categories";
import { getOverview } from "../lib/db";
import type { Category } from "../lib/types";
import { useAuth } from "../state/AuthContext";
import { I, LogoMark } from "./icons";
import { toast, useDataVersion } from "./ui";

export type Route = { view: "dashboard" } | { view: "category"; id: Category } | { view: "profile" };

function NavItem({
  icon,
  label,
  count,
  active,
  accent,
  onClick,
}: {
  icon: string;
  label: string;
  count?: number;
  active: boolean;
  accent?: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`group relative w-full flex items-center gap-2.5 px-3 py-[7.5px] rounded-lg text-[13.5px] font-medium transition-all duration-150 ${
        active ? "bg-mint/12 text-mint" : "text-mint/60 hover:text-mint hover:bg-mint/6"
      }`}
    >
      <span
        className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] rounded-r-full transition-all duration-200"
        style={{ height: active ? 18 : 0, background: accent ?? "var(--color-amber-bright)" }}
      />
      <span style={active && accent ? { color: accent === "#1e5c4f" ? "#7fc79b" : accent } : undefined}>
        <I name={icon} size={16} />
      </span>
      <span className="flex-1 text-left truncate">{label}</span>
      {count != null && count > 0 && (
        <span className="font-mono text-[10.5px] text-mint/45 group-hover:text-mint/70 tabular">{count}</span>
      )}
    </button>
  );
}

export function AppShell({
  route,
  onNavigate,
  children,
}: {
  route: Route;
  onNavigate: (r: Route) => void;
  children: ReactNode;
}) {
  const { user, logout, accessExp, refreshNow } = useAuth();
  const version = useDataVersion();
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [drawer, setDrawer] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const rotatedRef = useRef<string | null>(null);

  useEffect(() => {
    let on = true;
    getOverview()
      .then((o) => {
        if (on) setCounts(o.counts);
      })
      .catch(() => {});
    return () => {
      on = false;
    };
  }, [version]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const remaining = accessExp ? Math.max(0, accessExp - now) : 0;
  const mm = Math.floor(remaining / 60_000);
  const ss = Math.floor((remaining % 60_000) / 1000);
  const low = remaining > 0 && remaining < 5 * 60_000;

  // Transparent rotation the moment the access token lapses.
  useEffect(() => {
    if (accessExp && remaining <= 0) {
      const key = String(accessExp);
      if (rotatedRef.current !== key) {
        rotatedRef.current = key;
        refreshNow()
          .then(() => toast("Access token auto-rotated.", "info"))
          .catch(() => {});
      }
    }
  }, [remaining, accessExp, refreshNow]);

  const title =
    route.view === "dashboard"
      ? "Command deck"
      : route.view === "profile"
        ? "Profile & baselines"
        : CATEGORY_LIST.find((c) => c.id === route.id)?.label ?? "";
  const tagline =
    route.view === "dashboard"
      ? "Your signals against your own limits"
      : route.view === "profile"
        ? "Identity plus the thresholds you answer to"
        : CATEGORY_LIST.find((c) => c.id === route.id)?.tagline ?? "";

  const nav = (
    <>
      <div className="px-4 pt-6 pb-5 flex items-center gap-2.5">
        <LogoMark size={32} className="text-mint shrink-0" />
        <div>
          <div className="font-display font-bold text-[16.5px] leading-none text-mint">RiskLens</div>
          <div className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-mint/40 mt-1">console · m1</div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2.5 pb-4">
        <p className="px-3 pt-2 pb-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-mint/35">overview</p>
        <NavItem icon="grid" label="Command deck" active={route.view === "dashboard"} onClick={() => onNavigate({ view: "dashboard" })} />

        <p className="px-3 pt-5 pb-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-mint/35">data sources</p>
        {CATEGORY_LIST.map((c) => (
          <NavItem
            key={c.id}
            icon={c.icon}
            label={c.label}
            count={counts[c.id]}
            accent={c.accent}
            active={route.view === "category" && route.id === c.id}
            onClick={() => onNavigate({ view: "category", id: c.id })}
          />
        ))}

        <p className="px-3 pt-5 pb-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-mint/35">account</p>
        <NavItem icon="user" label="Profile & baselines" active={route.view === "profile"} onClick={() => onNavigate({ view: "profile" })} />
      </nav>

      <div className="border-t border-mint/10 p-3">
        <div className="flex items-center gap-2.5 rounded-lg bg-pine-ink/50 border border-mint/10 px-3 py-2.5">
          <div className="w-8 h-8 rounded-full bg-amber-bright/20 border border-amber-bright/40 text-amber-bright flex items-center justify-center font-display font-bold text-[14px]">
            {(user?.email?.[0] ?? "?").toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[12.5px] font-semibold text-mint truncate">{user?.email}</p>
            <p className="font-mono text-[10px] text-mint/40">session active</p>
          </div>
          <button
            onClick={() => {
              void logout().then(() => toast("Signed out — session revoked.", "info"));
            }}
            className="p-1.5 rounded-md text-mint/50 hover:text-coral hover:bg-coral/15 transition-colors focus-ring"
            title="Sign out"
            aria-label="Sign out"
          >
            <I name="logout" size={16} />
          </button>
        </div>
      </div>
    </>
  );

  return (
    <div className="min-h-screen bg-mist">
      {/* desktop sidebar */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-[250px] flex-col bg-pine-deep bg-console text-mint z-40">{nav}</aside>

      {/* mobile drawer */}
      {drawer && (
        <div className="lg:hidden fixed inset-0 z-50">
          <button aria-label="Close menu" className="absolute inset-0 bg-pine-ink/50" onClick={() => setDrawer(false)} />
          <aside
            className="absolute inset-y-0 left-0 w-[270px] flex flex-col bg-pine-deep bg-console text-mint shadow-pop"
            style={{ animation: "rl-drawer-in 0.28s cubic-bezier(0.22, 1, 0.36, 1) both" }}
          >
            {nav}
          </aside>
        </div>
      )}

      <div className="lg:pl-[250px]">
        <header className="sticky top-0 z-30 border-b border-line bg-mist/85 backdrop-blur-md">
          <div className="flex items-center gap-3 px-4 sm:px-7 h-[62px]">
            <button
              className="lg:hidden p-2 -ml-1 rounded-md text-ink-soft hover:text-ink hover:bg-pine/8 transition-colors focus-ring"
              onClick={() => setDrawer(true)}
              aria-label="Open menu"
            >
              <I name="menu" size={19} />
            </button>
            <div className="min-w-0 flex-1">
              <h1 className="font-display font-bold text-[17.5px] leading-tight text-ink truncate">{title}</h1>
              <p className="text-[12px] text-ink-faint truncate hidden sm:block">{tagline}</p>
            </div>

            <div
              className={`hidden sm:flex items-center gap-2 rounded-full border px-3 py-1.5 font-mono text-[11.5px] tabular transition-colors ${
                low ? "border-amber/40 bg-warn-soft text-amber" : "border-line-strong bg-panel text-ink-soft"
              }`}
              title="Access token time-to-live — rotates automatically"
            >
              <span className={`relative flex w-1.5 h-1.5 ${low ? "" : ""}`}>
                <span
                  className={`absolute inline-flex w-full h-full rounded-full ${low ? "bg-amber-bright" : "bg-moss-bright"}`}
                  style={{ animation: "rl-ping 2.2s cubic-bezier(0,0,0.2,1) infinite" }}
                />
                <span className={`relative inline-flex w-1.5 h-1.5 rounded-full ${low ? "bg-amber-bright" : "bg-moss-bright"}`} />
              </span>
              token {mm}:{String(ss).padStart(2, "0")}
            </div>
            <button
              onClick={() => {
                refreshNow()
                  .then(() => toast("Tokens rotated — new session issued.", "ok"))
                  .catch(() => toast("Rotation failed.", "err"));
              }}
              className="hidden sm:inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-panel px-2.5 py-1.5 text-[12px] font-semibold text-ink-soft hover:text-ink hover:border-moss/40 transition-colors focus-ring"
              title="Rotate refresh token now"
            >
              <I name="refresh" size={13} />
              rotate
            </button>
          </div>
        </header>

        <main className="px-4 sm:px-7 py-6 sm:py-8 max-w-[1180px] mx-auto">{children}</main>
      </div>
    </div>
  );
}
