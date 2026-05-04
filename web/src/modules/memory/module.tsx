import { lazy } from "react";
import { Brain } from "lucide-react";

import type { FrontendModule } from "../types";

const MemoryPage = lazy(async () => ({ default: (await import("./MemoryPage")).MemoryPage }));

export const memoryModule: FrontendModule = {
  key: "memory",
  name: "Memory",
  icon: Brain,
  section: "infrastructure",
  sidebar: { label: "Memory", href: "/modules/memory" },
  cards: [
    {
      title: "Memory",
      description: "Shared memory search, session index, candidate queue, and compaction controls.",
      href: "/modules/memory",
    },
  ],
  routes: [{ path: "/modules/memory", element: <MemoryPage /> }],
};
