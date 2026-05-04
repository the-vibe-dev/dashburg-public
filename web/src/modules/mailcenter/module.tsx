import { lazy } from "react";
import { Mail } from "lucide-react";

import type { FrontendModule } from "../types";

const MailCenterPage = lazy(async () => ({ default: (await import("./MailCenterPage")).MailCenterPage }));

export const mailCenterModule: FrontendModule = {
  key: "mailcenter",
  name: "MailCenter",
  icon: Mail,
  section: "operations",
  sidebar: { label: "MailCenter", href: "/modules/mailcenter" },
  cards: [
    {
      title: "MailCenter",
      description: "Unified inbox, threads, and subsystem processing visibility for Dashburg mail workflows.",
      href: "/modules/mailcenter",
    },
  ],
  routes: [{ path: "/modules/mailcenter", element: <MailCenterPage /> }],
};
