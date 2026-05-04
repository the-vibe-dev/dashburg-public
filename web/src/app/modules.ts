import { appgenModule } from "../modules/appgen/module";
import { discordModule } from "../modules/discord/module";
import { ideaVaultModule } from "../modules/ideavault/module";
import { localOpsModule } from "../modules/localops/module";
import { mailCenterModule } from "../modules/mailcenter/module";
import { memoryModule } from "../modules/memory/module";
import { nodeHealthModule } from "../modules/nodehealth/module";
import { orchestrationModule } from "../modules/orchestration/module";
import { projectsModule } from "../modules/projects/module";
import { remoteOpsModule } from "../modules/remoteops/module";
import { scheduleOpsModule } from "../modules/scheduleops/module";
import { skilledAgentsModule } from "../modules/skilledagents/module";
import { systemModule } from "../modules/system/module";
import { topicInsightsModule } from "../modules/topicinsights/module";
import { trendsModule } from "../modules/trends/module";
import { webAgentModule } from "../modules/webagent/module";
import type { FrontendModule } from "../modules/types";

export const builtinFrontendModules: FrontendModule[] = [
  projectsModule,
  memoryModule,
  localOpsModule,
  mailCenterModule,
  orchestrationModule,
  nodeHealthModule,
  remoteOpsModule,
  systemModule,
];

export const optionalFrontendModules: FrontendModule[] = [
  { ...ideaVaultModule, optional: true, packageKey: "ideavault" },
  { ...appgenModule, optional: true, packageKey: "idea-factory" },
  { ...topicInsightsModule, optional: true, packageKey: "topic-insights" },
  { ...trendsModule, optional: true, packageKey: "trends-researcher" },
  { ...discordModule, optional: true, packageKey: "discord-control" },
  { ...webAgentModule, optional: true, packageKey: "webagent" },
  { ...skilledAgentsModule, optional: true, packageKey: "skilled-agents" },
  { ...scheduleOpsModule, optional: true, packageKey: "schedule-ops" },
];

export const frontendModules = [...builtinFrontendModules, ...optionalFrontendModules];

export function resolveFrontendModules(installedOptionalKeys: string[]): FrontendModule[] {
  const enabled = new Set(installedOptionalKeys);
  return [
    ...builtinFrontendModules,
    ...optionalFrontendModules.filter((mod) => mod.packageKey && enabled.has(mod.packageKey)),
  ];
}
