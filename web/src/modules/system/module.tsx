import { lazy } from "react";
import { Cpu } from "lucide-react";
import type { FrontendModule } from "../types";

const SystemPage = lazy(async () => ({ default: (await import("./SystemPage")).SystemPage }));

export const systemModule: FrontendModule = {
  key: "system",
  name: "System",
  icon: Cpu,
  section: "infrastructure",
  sidebar: { label: "Settings", href: "/settings" },
  cards: [{ title: "System", description: "Health and runtime settings.", href: "/settings" }],
  routes: [{ path: "/settings", element: <SystemPage /> }],
};
