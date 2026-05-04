import type { ElementType, ReactNode } from "react";

export type DashboardCardDef = {
  title: string;
  description: string;
  href: string;
};

export type SidebarItemDef = {
  label: string;
  href: string;
};

export type RouteDef = {
  path: string;
  element: ReactNode;
};

export type SidebarSection = "content" | "operations" | "infrastructure";

export type FrontendModule = {
  key: string;
  name: string;
  sidebar: SidebarItemDef;
  cards: DashboardCardDef[];
  routes: RouteDef[];
  icon?: ElementType;
  section?: SidebarSection;
  optional?: boolean;
  packageKey?: string;
};
