import { useState } from "react";
import { dailyQuotes } from "./mockData";
import { I, LogoMark } from "./icons";
import { useAuth } from "../state/AuthContext";

export type NavRoute =
  | { view: "dashboard" }
  | { view: "category"; id: "fitness" | "habits" | "study" | "academic" | "goals" | "income_expense" | "savings" }
  | { view: "profile" }
  | { view: "reminders" };

interface NavItem {
  id: string;
  label: string;
  icon: string;
  route: NavRoute;
}

const NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: "dashboard", route: { view: "dashboard" } },
  { id: "activity", label: "Activity Tracker", icon: "activity", route: { view: "category", id: "fitness" } },
  { id: "habits", label: "Habit Tracker", icon: "check", route: { view: "category", id: "habits" } },
  { id: "productivity", label: "Productivity Analysis", icon: "brain", route: { view: "category", id: "study" } },
  { id: "focus", label: "Focus Sessions", icon: "target", route: { view: "category", id: "academic" } },
  { id: "goals", label: "Goals", icon: "flag", route: { view: "category", id: "goals" } },
  { id: "insights", label: "Insights & Reports", icon: "chart", route: { view: "category", id: "income_expense" } },
  { id: "calendar", label: "Calendar View", icon: "calendar", route: { view: "category", id: "savings" } },
  { id: "reminders", label: "Reminders", icon: "bell", route: { view: "reminders" } },
  { id: "settings", label: "Settings", icon: "settings", route: { view: "profile" } },
];

function isActive(route: NavRoute, current: NavRoute): boolean {
  if (route.view !== current.view) return false;
  if (route.view === "category" && current.view === "category") return route.id === current.id;
  return true;
}

export function Sidebar({
  route,
  onNavigate,
  mobileOpen,
  onCloseMobile,
}: {
  route: NavRoute;
  onNavigate: (r: NavRoute) => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const { user, logout } = useAuth();
  const [quote] = useState(() => dailyQuotes[Math.floor(Math.random() * dailyQuotes.length)]);
  const firstName = (user?.email?.split("@")[0] ?? "Sankari").replace(/[^a-zA-Z]/g, "");

  const content = (
    <>
      {/* Profile section */}
      <div className="px-5 pt-6 pb-4 border-b border-line">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-full bg-gradient-primary flex items-center justify-center text-white font-display font-bold text-[15px] shrink-0">
            {firstName.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[14px] font-semibold text-ink truncate">Hello, {firstName} 👋</p>
            <p className="text-[11.5px] text-ink-faint truncate">Focus on progress, not perfection.</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const active = isActive(item.route, route);
            return (
              <li key={item.id}>
                <button
                  onClick={() => {
                    onNavigate(item.route);
                    onCloseMobile();
                  }}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium transition-all duration-150 ${
                    active
                      ? "bg-gradient-primary text-white shadow-md"
                      : "text-ink-soft hover:text-ink hover:bg-bg-soft"
                  }`}
                >
                  <I name={item.icon} size={18} />
                  <span className="flex-1 text-left">{item.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Daily quote card */}
      <div className="px-3 pb-3">
        <div className="relative rounded-xl bg-gradient-primary-soft border border-primary/15 p-4 overflow-hidden">
          <div className="absolute top-0 right-0 w-20 h-20 rounded-full bg-primary/10 -translate-y-8 translate-x-8" />
          <div className="absolute bottom-0 left-0 w-16 h-16 rounded-full bg-primary/10 translate-y-6 -translate-x-6" />
          <div className="relative">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-primary/70 mb-1.5">Daily Quote</p>
            <p className="text-[12.5px] text-ink leading-relaxed italic">"{quote}"</p>
          </div>
        </div>
      </div>

      {/* Logout */}
      <div className="px-3 pb-4 border-t border-line pt-3">
        <button
          onClick={() => {
            void logout();
          }}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium text-ink-soft hover:text-danger hover:bg-danger-soft transition-colors"
        >
          <I name="logout" size={18} />
          <span>Sign out</span>
        </button>
      </div>
    </>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-[260px] flex-col bg-sidebar border-r border-line z-40">
        {content}
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <button aria-label="Close menu" className="absolute inset-0 bg-ink/40" onClick={onCloseMobile} />
          <aside className="anim-slide-left absolute inset-y-0 left-0 w-[280px] flex flex-col bg-sidebar shadow-lg">
            <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-line">
              <div className="flex items-center gap-2.5">
                <LogoMark size={28} />
                <span className="font-display font-bold text-[15px] text-ink">Productivity Engine</span>
              </div>
              <button onClick={onCloseMobile} className="p-1.5 rounded-md text-ink-faint hover:text-ink hover:bg-bg-soft">
                <I name="x" size={16} />
              </button>
            </div>
            {content}
          </aside>
        </div>
      )}
    </>
  );
}
