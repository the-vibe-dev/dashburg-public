import { lazy } from "react";
import { Workflow } from "lucide-react";
import type { FrontendModule } from "../types";

const OrchestrationPage = lazy(async () => ({ default: (await import("./OrchestrationPages")).OrchestrationPage }));

export const orchestrationModule: FrontendModule = {
  key: "orchestration",
  name: "Orchestration",
  icon: Workflow,
  section: "operations",
  sidebar: { label: "Orchestration", href: "/modules/orchestration" },
  cards: [
    {
      title: "Orchestration",
      description: "Delegated multi-node Codex orchestration with node-local workers. LocalOps remains the direct/manual path.",
      href: "/modules/orchestration",
    },
  ],
  routes: [
    { path: "/modules/orchestration", element: <OrchestrationPage /> },
    { path: "/modules/orchestration/jobs/:id", element: <OrchestrationPage /> },
  ],
};
