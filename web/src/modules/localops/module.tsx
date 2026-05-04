import { lazy } from "react";
import { Terminal } from "lucide-react";
import type { FrontendModule } from "../types";

const LocalOpsChatPage = lazy(async () => ({ default: (await import("./LocalOpsPages")).LocalOpsChatPage }));
const LocalOpsSettingsPage = lazy(async () => ({ default: (await import("./LocalOpsPages")).LocalOpsSettingsPage }));

export const localOpsModule: FrontendModule = {
  key: "localops",
  name: "LocalOps",
  icon: Terminal,
  section: "infrastructure",
  sidebar: { label: "LocalOps", href: "/modules/local-ops/chat" },
  cards: [
    {
      title: "LocalOps",
      description: "Local chat orchestrator with OpenAI API keys, Ollama providers, and workspace agents.",
      href: "/modules/local-ops/chat",
    },
  ],
  routes: [
    { path: "/modules/local-ops/chat", element: <LocalOpsChatPage /> },
    { path: "/modules/local-ops/settings", element: <LocalOpsSettingsPage /> },
  ],
};
