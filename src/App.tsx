import { useEffect, useMemo, useState } from "react";
import { Sun, Moon } from "lucide-react";
import { Sidebar, type NavRoute } from "./components/Sidebar";
import { Dashboard } from "./components/Dashboard";
import { CategoryPage } from "./components/CategoryPage";
import { ProfilePage } from "./components/ProfilePage";
import { SimulationLab } from "./components/SimulationLab";
import { LogoMark } from "./components/icons";
import { I } from "./components/icons";
import { ToastHost } from "./components/ui";
import { AuthProvider, useAuth } from "./state/AuthContext";
import { ThemeProvider, useTheme } from "./state/ThemeContext";
import { AuthGate } from "./components/AuthGate";

function BootScreen() {
  return (
    <div className="min-h-screen bg-bg flex flex-col items-center justify-center gap-5">
      <LogoMark size={54} />
      <div className="text-center">
        <p className="font-display font-bold text-[19px] text-ink">Productivity Engine</p>
        <p className="mt-1.5 font-mono text-[11.5px] uppercase tracking-[0.22em] text-ink-faint anim-blink">
          verifying session…
        </p>
      </div>
    </div>
  );
}

function RemindersView() {
  return (
    <div className="rounded-xl border border-line bg-card p-8 shadow-sm text-center">
      <div className="w-14 h-14 rounded-2xl bg-primary-soft border border-primary/15 flex items-center justify-center text-primary mx-auto mb-4">
        <I name="bell" size={26} sw={1.5} />
      </div>
      <h3 className="font-display text-lg font-semibold text-ink">Reminders</h3>
      <p className="mt-2 text-sm text-ink-soft max-w-[400px] mx-auto">
        Reminder notifications are coming in the next milestone. You'll be able to set recurring reminders for habits, focus sessions, and goals.
      </p>
    </div>
  );
}

function Gate() {
  const { status } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [route, setRoute] = useState<NavRoute>({ view: "dashboard" });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem("sidebar_collapsed") === "true";
    } catch {
      return false;
    }
  });

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("sidebar_collapsed", String(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

  // Date range state
  const [timeframe, setTimeframe] = useState<"this_week" | "last_week" | "this_month">("this_week");

  const { startDate, endDate, dateLabel } = useMemo(() => {
    const now = new Date();
    const dayOfWeek = now.getDay(); // 0=Sun, 1=Mon, ..., 6=Sat
    const diffToMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
    const fmt = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

    if (timeframe === "this_week") {
      const start = new Date(now);
      start.setDate(now.getDate() - diffToMonday);
      start.setHours(0, 0, 0, 0);
      const end = new Date(start);
      end.setDate(start.getDate() + 6);
      end.setHours(23, 59, 59, 999);
      return { startDate: start.toISOString().slice(0, 10), endDate: end.toISOString().slice(0, 10), dateLabel: `${fmt(start)} – ${fmt(end)}` };
    } else if (timeframe === "last_week") {
      const thisMonday = new Date(now);
      thisMonday.setDate(now.getDate() - diffToMonday);
      const start = new Date(thisMonday);
      start.setDate(thisMonday.getDate() - 7);
      start.setHours(0, 0, 0, 0);
      const end = new Date(start);
      end.setDate(start.getDate() + 6);
      end.setHours(23, 59, 59, 999);
      return { startDate: start.toISOString().slice(0, 10), endDate: end.toISOString().slice(0, 10), dateLabel: `${fmt(start)} – ${fmt(end)}` };
    } else {
      const start = new Date(now.getFullYear(), now.getMonth(), 1);
      const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
      return { startDate: start.toISOString().slice(0, 10), endDate: end.toISOString().slice(0, 10), dateLabel: `${fmt(start)} – ${fmt(end)}` };
    }
  }, [timeframe]);

  useEffect(() => {
    if (status === "guest") setRoute({ view: "dashboard" });
  }, [status]);

  if (status === "booting") return <BootScreen />;
  if (status === "guest") return <AuthGate />;

  const title =
    route.view === "dashboard"
      ? "Productivity & Habit Analysis Engine ✧"
      : route.view === "profile"
        ? "Settings"
        : route.view === "reminders"
          ? "Reminders"
          : route.view === "simulation"
            ? "Simulation Lab ✧"
            : "Overview";

  const subtitle =
    route.view === "dashboard"
      ? "Track. Analyze. Improve. Every day."
      : route.view === "profile"
        ? "Manage your profile and preferences"
        : route.view === "reminders"
          ? "Stay on track with timely reminders"
          : route.view === "simulation"
            ? "Run what-if scenarios on your real data"
            : "Your personal analytics";

  return (
    <div className="min-h-screen bg-bg transition-colors duration-200">
      <Sidebar
        route={route}
        onNavigate={setRoute}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        collapsed={sidebarCollapsed}
        onToggleCollapse={toggleSidebar}
      />

      <div
        className={`transition-all duration-300 ease-in-out ${
          sidebarCollapsed ? "lg:pl-[76px]" : "lg:pl-[260px]"
        }`}
      >
        {/* Top header */}
        <header className="sticky top-0 z-30 border-b border-line bg-card/90 backdrop-blur-md transition-colors duration-200">
          <div className="flex items-center gap-3 px-5 sm:px-7 h-[64px]">
            <button
              className="lg:hidden p-2 -ml-1 rounded-md text-ink-soft hover:text-ink hover:bg-bg-soft transition-colors focus-ring"
              onClick={() => setMobileOpen(true)}
              aria-label="Open menu"
            >
              <I name="menu" size={19} />
            </button>
            <div className="min-w-0 flex-1">
              <h1 className="font-display font-bold text-[17px] leading-tight text-ink truncate">{title}</h1>
              <p className="text-[12px] text-ink-faint truncate hidden sm:block">{subtitle}</p>
            </div>

            {/* Right actions */}
            <div className="flex items-center gap-2.5">
              {/* Date indicator */}
              <div className="hidden sm:flex items-center gap-2 rounded-lg border border-line bg-bg-soft px-3 py-1.5 text-[12.5px] text-ink-soft">
                <I name="calendar" size={14} />
                <span>{dateLabel}</span>
              </div>

              {/* Light/Dark Mode Theme Toggle */}
              <button
                onClick={toggleTheme}
                className="p-2 rounded-lg border border-line bg-bg-soft text-ink-soft hover:text-ink hover:bg-card transition-all duration-150 shadow-xs focus-ring"
                title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
                aria-label={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
              >
                {theme === "dark" ? (
                  <Sun size={16} className="text-warn transition-transform duration-200 rotate-0 hover:rotate-45" />
                ) : (
                  <Moon size={16} className="text-primary transition-transform duration-200 rotate-0 hover:-rotate-12" />
                )}
              </button>

              {/* Timeframe select */}
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value as "this_week" | "last_week" | "this_month")}
                className="text-[12.5px] font-medium text-ink border border-line rounded-lg px-3 py-1.5 bg-card hover:bg-bg-soft transition-colors focus-ring cursor-pointer"
              >
                <option value="this_week">This Week</option>
                <option value="last_week">Last Week</option>
                <option value="this_month">This Month</option>
              </select>
            </div>
          </div>
        </header>

        <main className="px-4 sm:px-6 lg:px-7 py-5 max-w-[1500px]">
          {route.view === "dashboard" ? (
            <Dashboard onNavigate={setRoute} startDate={startDate} endDate={endDate} />
          ) : route.view === "category" ? (
            <CategoryPage key={route.id} category={route.id} />
          ) : route.view === "simulation" ? (
            <SimulationLab onNavigate={setRoute} />
          ) : route.view === "reminders" ? (
            <RemindersView />
          ) : (
            <ProfilePage />
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Gate />
        <ToastHost />
      </AuthProvider>
    </ThemeProvider>
  );
}
