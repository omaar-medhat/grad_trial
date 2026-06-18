import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, BarChart3, MessageCircle, User, LogOut, Menu, X, AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";

const navItems = [
  { to: "/",          icon: LayoutDashboard, label: "Dashboard" },
  { to: "/analytics", icon: BarChart3,       label: "Analytics" },
  { to: "/alerts",    icon: AlertTriangle,   label: "Alerts" },
  { to: "/chat",      icon: MessageCircle,   label: "Assistant" },
  { to: "/profile",   icon: User,            label: "Profile" },
];

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useAuth();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const initials =
    (user?.email?.[0] || "U").toUpperCase();

  return (
    <div className="flex min-h-screen bg-background">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-foreground/30 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border bg-card transition-transform lg:static lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex items-center gap-3 border-b border-border px-5 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl overflow-hidden shadow-sm border border-border bg-card">
            <img src="/logo.png" alt="PulseGuard AI" className="h-full w-full object-contain" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-foreground">PulseGuard AI</h1>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Health Companion</p>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="ml-auto lg:hidden" aria-label="Close menu">
            <X className="h-5 w-5 text-muted-foreground" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-4">
          {navItems.map(({ to, icon: Icon, label }) => {
            const active = location.pathname === to;
            return (
              <Link
                key={to}
                to={to}
                onClick={() => setSidebarOpen(false)}
                className={cn(
                  "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
                  active
                    ? "bg-primary/10 text-primary shadow-sm"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                )}
              >
                <Icon className={cn("h-4 w-4 transition-transform", active && "scale-110")} />
                {label}
                {active && (
                  <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border p-3">
          <div className="mb-2 flex items-center gap-3 rounded-xl bg-secondary/50 p-2.5">
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary">
              {initials}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-foreground">{user?.email}</p>
              {user?.isDemo && <p className="text-[10px] text-muted-foreground">Demo session</p>}
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-2 text-muted-foreground hover:text-foreground"
            onClick={signOut}
          >
            <LogOut className="h-4 w-4" /> Sign out
          </Button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-card/85 px-4 py-3 backdrop-blur-md lg:hidden">
          <button onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            <Menu className="h-5 w-5 text-foreground" />
          </button>
          <div className="flex h-7 w-7 items-center justify-center rounded-lg overflow-hidden border border-border">
            <img src="/logo.png" alt="Logo" className="h-full w-full object-contain" />
          </div>
          <span className="text-sm font-bold text-foreground">PulseGuard AI</span>
        </header>
        <main className="flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
