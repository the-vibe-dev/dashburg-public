import { localOpsModule } from "../modules/localops/module";
import { mailCenterModule } from "../modules/mailcenter/module";
import { memoryModule } from "../modules/memory/module";
import { nodeHealthModule } from "../modules/nodehealth/module";
import { orchestrationModule } from "../modules/orchestration/module";
import { projectsModule } from "../modules/projects/module";
import { remoteOpsModule } from "../modules/remoteops/module";
import { systemModule } from "../modules/system/module";

export const frontendModules = [
  projectsModule,
  memoryModule,
  localOpsModule,
  mailCenterModule,
  orchestrationModule,
  nodeHealthModule,
  remoteOpsModule,
  systemModule,
];
