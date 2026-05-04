import { lazy } from "react";
import { FolderKanban } from "lucide-react";
import type { FrontendModule } from "../types";

const ProjectDetailPage = lazy(async () => ({ default: (await import("./ProjectsPage")).ProjectDetailPage }));
const ProjectsListPage = lazy(async () => ({ default: (await import("./ProjectsPage")).ProjectsListPage }));
const ProjectsWorkspacePage = lazy(async () => ({ default: (await import("./ProjectsWorkspacePage")).ProjectsWorkspacePage }));

export const projectsModule: FrontendModule = {
  key: "projects",
  name: "TaskVault",
  icon: FolderKanban,
  section: "content",
  sidebar: { label: "TaskVault", href: "/projects" },
  cards: [{ title: "TaskVault", description: "Notion-lite planning workspace.", href: "/projects" }],
  routes: [
    { path: "/projects", element: <ProjectsListPage /> },
    { path: "/projects/:id", element: <ProjectDetailPage /> },
    { path: "/projects/:id/workspace", element: <ProjectsWorkspacePage /> },
  ],
};
