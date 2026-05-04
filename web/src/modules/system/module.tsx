import { lazy } from "react";
import { Cpu } from "lucide-react";
import type { FrontendModule } from "../types";

const SystemPage = lazy(async () => ({ default: (await import("./SystemPage")).SystemPage }));
const AddModulesPage = lazy(async () => ({ default: (await import("./AddModulesPage")).AddModulesPage }));

export const systemModule: FrontendModule = {
  key: "system",
  name: "System",
  icon: Cpu,
  section: "infrastructure",
  sidebar: { label: "Settings", href: "/settings" },
  cards: [{ title: "System", description: "Health, runtime settings, and installable module management.", href: "/settings" }],
  routes: [
    { path: "/settings", element: <SystemPage /> },
    { path: "/settings/modules", element: <AddModulesPage /> },
  ],
};
