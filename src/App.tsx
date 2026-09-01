import { useEffect, useState } from "react";
import { AppShell, type Route } from "./components/AppShell";
import { AuthGate } from "./components/AuthGate";
import { CategoryPage } from "./components/CategoryPage";
import { Dashboard } from "./components/Dashboard";
import { LogoMark } from "./components/icons";
import { ProfilePage } from "./components/ProfilePage";
import { ToastHost } from "./components/ui";
import { AuthProvider, useAuth } from "./state/AuthContext";

function BootScreen() {
  return (
    <div className="min-h-screen bg-pine-deep bg-console flex flex-col items-center justify-center gap-5 text-mint">
      <LogoMark size={54} className="text-mint" />
      <div className="text-center">
        <p className="font-display font-bold text-[19px]">RiskLens</p>
        <p className="mt-1.5 font-mono text-[11.5px] uppercase tracking-[0.22em] text-mint/50 anim-blink">
          verifying session…
        </p>
      </div>
    </div>
  );
}

function Gate() {
  const { status } = useAuth();
  const [route, setRoute] = useState<Route>({ view: "dashboard" });

  useEffect(() => {
    if (status === "guest") setRoute({ view: "dashboard" });
  }, [status]);

  if (status === "booting") return <BootScreen />;
  if (status === "guest") return <AuthGate />;

  return (
    <AppShell route={route} onNavigate={setRoute}>
      {route.view === "dashboard" ? (
        <Dashboard onNavigate={setRoute} />
      ) : route.view === "category" ? (
        <CategoryPage key={route.id} category={route.id} />
      ) : (
        <ProfilePage />
      )}
    </AppShell>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
      <ToastHost />
    </AuthProvider>
  );
}
