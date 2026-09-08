import { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";
import { Sidebar, type NavRoute } from "./components/Sidebar";
import { Dashboard } from "./components/Dashboard";
import { CategoryPage } from "./components/CategoryPage";
import { ProfilePage } from "./components/ProfilePage";
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
          : "Overview";

  const subtitle =
    route.view === "dashboard"
      ? "Track. Analyze. Improve. Every day."
      : route.view === "profile"
        ? "Manage your profile and preferences"
        : route.view === "reminders"
          ? "Stay on track with timely reminders"
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
                <span>May 12 – May 18, 2026</span>
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
              <select className="text-[12.5px] font-medium text-ink border border-line rounded-lg px-3 py-1.5 bg-card hover:bg-bg-soft transition-colors focus-ring cursor-pointer">
                <option>This Week</option>
                <option>Last Week</option>
                <option>This Month</option>
              </select>
            </div>
          </div>
        </header>

        <main className="px-4 sm:px-6 lg:px-7 py-5 max-w-[1500px]">
          {route.view === "dashboard" ? (
            <Dashboard />
          ) : route.view === "category" ? (
            <CategoryPage key={route.id} category={route.id} />
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
