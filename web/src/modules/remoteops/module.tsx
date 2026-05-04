import { lazy } from "react";
import { Network } from "lucide-react";
import type { FrontendModule } from "../types";

const RemoteCodexJobsPage = lazy(async () => ({ default: (await import("./RemoteOpsPages")).RemoteCodexJobsPage }));
const RemoteJobDetailPage = lazy(async () => ({ default: (await import("./RemoteOpsPages")).RemoteJobDetailPage }));
const RemoteJobsPage = lazy(async () => ({ default: (await import("./RemoteOpsPages")).RemoteJobsPage }));
const RemoteNodeDetailPage = lazy(async () => ({ default: (await import("./RemoteOpsPages")).RemoteNodeDetailPage }));
const RemoteNodesPage = lazy(async () => ({ default: (await import("./RemoteOpsPages")).RemoteNodesPage }));
const RemoteSettingsPage = lazy(async () => ({ default: (await import("./RemoteOpsPages")).RemoteSettingsPage }));
const RemoteTerminalPage = lazy(async () => ({ default: (await import("./RemoteOpsPages")).RemoteTerminalPage }));

export const remoteOpsModule: FrontendModule = {
  key: "remote_ops",
  name: "RemoteOps",
  icon: Network,
  section: "infrastructure",
  sidebar: { label: "RemoteOps", href: "/modules/remote-ops" },
  cards: [
    {
      title: "RemoteOps",
      description: "Control Center for nodes, jobs, codex runs, and interactive terminal sessions.",
      href: "/modules/remote-ops/nodes",
    },
  ],
  routes: [
    { path: "/modules/remote-ops", element: <RemoteNodesPage /> },
    { path: "/modules/remote-ops/nodes", element: <RemoteNodesPage /> },
    { path: "/modules/remote-ops/nodes/:id", element: <RemoteNodeDetailPage /> },
    { path: "/modules/remote-ops/servers", element: <RemoteNodesPage /> },
    { path: "/modules/remote-ops/servers/:id", element: <RemoteNodeDetailPage /> },
    { path: "/modules/remote-ops/jobs", element: <RemoteJobsPage /> },
    { path: "/modules/remote-ops/jobs/:id", element: <RemoteJobDetailPage /> },
    { path: "/modules/remote-ops/codex", element: <RemoteCodexJobsPage /> },
    { path: "/modules/remote-ops/terminal", element: <RemoteTerminalPage /> },
    { path: "/modules/remote-ops/settings", element: <RemoteSettingsPage /> },
  ],
};
