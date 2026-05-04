import { Suspense, useMemo, useState } from "react";
import type { ElementType } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ChevronLeft, ChevronRight, LayoutDashboard, Moon, Sun } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { DashboardPage } from "./DashboardPage";
import { resolveFrontendModules } from "./modules";
import { useDashburgSSE } from "../shared/api/hooks";
import { apiGet } from "../shared/api/client";
import { useTheme } from "./ThemeContext";
import type { FrontendModule, SidebarSection } from "../modules/types";
import { Skeleton } from "../shared/components/ui/skeleton";

const SIDEBAR_WIDE = 248;
const SIDEBAR_NARROW = 56;

const SECTION_LABELS: Record<SidebarSection, string> = {
  content: "Knowledge",
  operations: "Execution",
  infrastructure: "Control",
};

const SECTION_ORDER: SidebarSection[] = ["infrastructure", "operations", "content"];

export function App() {
  useDashburgSSE();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const [collapsed, setCollapsed] = useState<boolean>(() => localStorage.getItem("dashgithub-sidebar-collapsed") === "true");
  const installedQuery = useQuery({
    queryKey: ["module-system", "installed"],
    queryFn: () => apiGet<{ installed: string[] }>("/api/module-system/installed"),
    staleTime: 10_000,
  });

  const frontendModules = useMemo(
    () => resolveFrontendModules(installedQuery.data?.installed ?? []),
    [installedQuery.data?.installed],
  );

  const groupedModules = useMemo(() => {
    const groups = new Map<SidebarSection, FrontendModule[]>();
    for (const section of SECTION_ORDER) groups.set(section, []);
    for (const mod of frontendModules) {
      const section = mod.section ?? "operations";
      groups.get(section)?.push(mod);
    }
    return groups;
  }, [frontendModules]);

  const sidebarWidth = collapsed ? SIDEBAR_NARROW : SIDEBAR_WIDE;
  const isActiveRoute = (href: string) => location.pathname === href || location.pathname.startsWith(`${href}/`);

  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("dashgithub-sidebar-collapsed", String(next));
  }

  return (
    <div className="min-h-screen">
      <aside className={`sidebar ${collapsed ? "sidebar-collapsed" : "sidebar-expanded"}`} style={{ width: sidebarWidth }}>
        <div className="px-3 py-4">
          <Link to="/" className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/30 bg-primary/10 text-primary font-semibold">
              DG
            </div>
            <div className="sidebar-label min-w-0">
              <p className="truncate font-display text-[15px] font-bold text-white/95">Dashgithub</p>
              <p className="truncate text-[11px] uppercase tracking-[0.12em] text-white/40">Control Plane</p>
            </div>
          </Link>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-3">
          <NavLink href="/" label="Command Center" icon={LayoutDashboard} current={location.pathname === "/"} collapsed={collapsed} />
          {SECTION_ORDER.map((section) => {
            const modules = groupedModules.get(section) ?? [];
            if (!modules.length) return null;
            return (
              <div key={section} className="mt-3">
                {!collapsed ? <div className="sidebar-section-label">{SECTION_LABELS[section]}</div> : <div className="mx-2 my-2 h-px bg-white/8" />}
                <div className="space-y-1">
                  {modules.map((mod) => (
                    <NavLink
                      key={mod.key}
                      href={mod.sidebar.href}
                      label={mod.sidebar.label}
                      icon={mod.icon}
                      current={isActiveRoute(mod.sidebar.href)}
                      collapsed={collapsed}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        <div className="border-t border-white/8">
          <button
            onClick={toggleTheme}
            className="flex w-full items-center gap-2.5 px-3 py-2.5 text-white/50 hover:text-white/85 transition-colors"
            title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            <div className="w-7 flex items-center justify-center shrink-0">{theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}</div>
            <span className="sidebar-label text-[12px] font-medium">{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          </button>
          <button
            onClick={toggleCollapsed}
            className="flex w-full items-center gap-2.5 px-3 py-2.5 text-white/50 hover:text-white/85 transition-colors"
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <div className="w-7 flex items-center justify-center shrink-0">{collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}</div>
            <span className="sidebar-label text-[12px] font-medium">Collapse</span>
          </button>
        </div>
      </aside>

      <main className="min-h-screen min-w-0 p-4 md:p-6" style={{ marginLeft: sidebarWidth }}>
        <div className="mx-auto max-w-[1600px]">
          <Routes>
            <Route path="/" element={<Suspense fallback={<RouteLoadingFallback />}><DashboardPage modules={frontendModules} /></Suspense>} />
            {frontendModules.flatMap((m) => m.routes).map((r) => (
              <Route key={r.path} path={r.path} element={<Suspense fallback={<RouteLoadingFallback />}>{r.element}</Suspense>} />
            ))}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}

function RouteLoadingFallback() {
  return (
    <div className="space-y-4 animate-fade-up">
      <Skeleton className="h-24 w-full" />
      <div className="grid gap-4 md:grid-cols-3">
        <Skeleton className="h-36" />
        <Skeleton className="h-36" />
        <Skeleton className="h-36" />
      </div>
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

function NavLink({ href, label, icon: Icon, current, collapsed }: { href: string; label: string; icon?: ElementType; current: boolean; collapsed: boolean }) {
  const IconComponent = Icon ?? LayoutDashboard;
  return (
    <Link
      to={href}
      className={`sidebar-nav-link group flex items-center gap-2.5 rounded-xl px-2.5 py-2.5 text-sm font-medium transition-all duration-150 ${
        current ? "active bg-white/10 text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]" : "text-white/60 hover:bg-white/6 hover:text-white/90"
      }`}
    >
      <div className="flex w-7 shrink-0 items-center justify-center"><IconComponent size={15} /></div>
      <span className="sidebar-label min-w-0 truncate">{label}</span>
      {!collapsed && current ? <span className="ml-auto h-2 w-2 rounded-full bg-primary" /> : null}
    </Link>
  );
}
