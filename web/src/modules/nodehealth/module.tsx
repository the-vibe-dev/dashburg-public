import { lazy } from "react";
import { Activity } from "lucide-react";
import type { FrontendModule } from "../types";

const RemoteNodeHealthPage = lazy(async () => ({ default: (await import("../remoteops/RemoteOpsPages")).RemoteNodeHealthPage }));

export const nodeHealthModule: FrontendModule = {
  key: "node_health",
  name: "NodeHealth",
  icon: Activity,
  section: "infrastructure",
  sidebar: { label: "NodeHealth", href: "/modules/node-health" },
  cards: [
    {
      title: "NodeHealth",
      description: "Dedicated host monitoring board for all RemoteOps nodes.",
      href: "/modules/node-health",
    },
  ],
  routes: [{ path: "/modules/node-health", element: <RemoteNodeHealthPage /> }],
};
