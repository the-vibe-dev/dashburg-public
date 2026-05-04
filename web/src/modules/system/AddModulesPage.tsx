import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "../../shared/api/client";
import { Button } from "../../shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../shared/components/ui/card";
import { PageHeader } from "../../shared/components/ui/page-header";


type ModuleCatalogItem = {
  key: string;
  name: string;
  version: string;
  description: string;
  installed: boolean;
  runtime?: {
    mode?: string;
    service_dir?: string;
    default_port?: number;
    start_command?: string;
    env_file?: string;
    notes?: string;
  };
  dependencies: {
    modules: string[];
    core_capabilities: string[];
  };
  validation: {
    ok: boolean;
    installed: boolean;
    backend_import_ok: boolean;
    backend_error: string;
    files_dir_ok: boolean;
    frontend_entry_ok: boolean;
    missing_modules: string[];
    missing_core_capabilities: string[];
    runtime?: {
      mode?: string;
      service_dir?: string;
      service_dir_ok?: boolean;
      default_port?: number;
      start_command?: string;
      env_file?: string;
      notes?: string;
    };
    smoke?: {
      solo_harness: boolean;
      host_install: boolean;
    };
  };
};

export function AddModulesPage() {
  const queryClient = useQueryClient();
  const catalogQuery = useQuery({
    queryKey: ["module-system", "catalog"],
    queryFn: () => apiGet<ModuleCatalogItem[]>("/api/module-system/catalog"),
    refetchInterval: 15_000,
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["module-system"] });
  };

  const installMutation = useMutation({
    mutationFn: (key: string) => apiPost("/api/module-system/install", { key }),
    onSuccess: refresh,
  });

  const validateMutation = useMutation({
    mutationFn: (key: string) => apiPost("/api/module-system/validate", { key }),
  });

  const runtimeBootstrapMutation = useMutation({
    mutationFn: (key: string) => apiPost("/api/module-system/runtime/bootstrap", { key }),
    onSuccess: refresh,
  });

  const runtimeBootstrapAllMutation = useMutation({
    mutationFn: () => apiPost("/api/module-system/runtime/bootstrap-all", {}),
    onSuccess: refresh,
  });

  const runtimeInstallServiceMutation = useMutation({
    mutationFn: (key: string) => apiPost("/api/module-system/runtime/install-service", { key }),
  });

  const runtimeStatusMutation = useMutation({
    mutationFn: (key: string) => apiPost("/api/module-system/runtime/status", { key }),
  });

  const uninstallMutation = useMutation({
    mutationFn: (key: string) => apiPost("/api/module-system/uninstall", { key }),
    onSuccess: refresh,
  });

  const items = catalogQuery.data ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        compact
        title="Add Modules"
        description="Install optional Dashburg modules from the sibling dashburg-modules pack repo. Dependencies are resolved automatically."
      />

      <Card>
        <CardHeader>
          <CardTitle>Module Catalog</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => runtimeBootstrapAllMutation.mutate()} disabled={runtimeBootstrapAllMutation.isPending}>
              Bootstrap All Installed Runtimes
            </Button>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {items.map((item) => {
              const validation = item.validation;
              const busy = installMutation.isPending || uninstallMutation.isPending || validateMutation.isPending || runtimeBootstrapMutation.isPending || runtimeBootstrapAllMutation.isPending || runtimeInstallServiceMutation.isPending || runtimeStatusMutation.isPending;
              return (
                <div key={item.key} className="rounded-xl border border-border/70 bg-background/20 p-4 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-foreground">{item.name}</p>
                      <p className="text-xs uppercase tracking-[0.12em] text-muted-foreground">{item.key} • v{item.version}</p>
                    </div>
                    <span className={`rounded-full px-2 py-1 text-[11px] font-medium ${item.installed ? "bg-success/10 text-success" : "bg-warning/10 text-warning"}`}>
                      {item.installed ? "Installed" : "Available"}
                    </span>
                  </div>

                  <p className="text-sm text-muted-foreground">{item.description || "No description provided."}</p>

                  <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                    <div>
                      <p className="font-medium text-foreground">Module deps</p>
                      <p>{item.dependencies.modules.length ? item.dependencies.modules.join(", ") : "None"}</p>
                    </div>
                    <div>
                      <p className="font-medium text-foreground">Core deps</p>
                      <p>{item.dependencies.core_capabilities.length ? item.dependencies.core_capabilities.join(", ") : "None"}</p>
                    </div>
                    <div>
                      <p className="font-medium text-foreground">Validation</p>
                      <p>{validation.ok ? "Ready" : "Needs attention"}</p>
                    </div>
                    <div>
                      <p className="font-medium text-foreground">Runtime mode</p>
                      <p>{item.runtime?.mode ?? validation.runtime?.mode ?? "host-only"}</p>
                    </div>
                    <div>
                      <p className="font-medium text-foreground">Solo smoke</p>
                      <p>{validation.smoke?.solo_harness ? "Pass" : "Fail"}</p>
                    </div>
                  </div>

                  {(item.runtime?.service_dir || validation.runtime?.service_dir || item.runtime?.start_command || validation.runtime?.start_command) ? (
                    <div className="rounded-lg border border-border/70 bg-background/20 p-3 text-xs text-muted-foreground space-y-1">
                      <p><span className="font-medium text-foreground">Service dir:</span> {item.runtime?.service_dir || validation.runtime?.service_dir || "-"}</p>
                      <p><span className="font-medium text-foreground">Default port:</span> {String(item.runtime?.default_port ?? validation.runtime?.default_port ?? "-")}</p>
                      <p><span className="font-medium text-foreground">Start:</span> {item.runtime?.start_command || validation.runtime?.start_command || "-"}</p>
                      <p><span className="font-medium text-foreground">Notes:</span> {item.runtime?.notes || validation.runtime?.notes || "-"}</p>
                    </div>
                  ) : null}

                  {validation.backend_error ? (
                    <div className="rounded-lg border border-danger/30 bg-danger/5 p-3 text-xs text-danger whitespace-pre-wrap">{validation.backend_error}</div>
                  ) : null}

                  {validation.missing_modules.length || validation.missing_core_capabilities.length ? (
                    <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-warning space-y-1">
                      {validation.missing_modules.length ? <p>Missing modules: {validation.missing_modules.join(", ")}</p> : null}
                      {validation.missing_core_capabilities.length ? <p>Missing core capabilities: {validation.missing_core_capabilities.join(", ")}</p> : null}
                    </div>
                  ) : null}

                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => installMutation.mutate(item.key)} disabled={busy || item.installed}>
                      Install
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => validateMutation.mutate(item.key)} disabled={busy}>
                      Validate
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => runtimeStatusMutation.mutate(item.key)} disabled={busy}>
                      Runtime
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => runtimeBootstrapMutation.mutate(item.key)} disabled={busy || !item.installed}>
                      Bootstrap
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => runtimeInstallServiceMutation.mutate(item.key)} disabled={busy || !item.installed}>
                      Install Service
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => uninstallMutation.mutate(item.key)} disabled={busy || !item.installed}>
                      Uninstall
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {validateMutation.data ? (
        <Card>
          <CardHeader>
            <CardTitle>Last Validation</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto rounded-xl border border-border/70 bg-background/20 p-4 text-xs text-muted-foreground">
              {JSON.stringify(validateMutation.data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      ) : null}

      {runtimeBootstrapMutation.data ? (
        <Card>
          <CardHeader>
            <CardTitle>Last Runtime Bootstrap</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto rounded-xl border border-border/70 bg-background/20 p-4 text-xs text-muted-foreground">
              {JSON.stringify(runtimeBootstrapMutation.data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      ) : null}

      {runtimeBootstrapAllMutation.data ? (
        <Card>
          <CardHeader>
            <CardTitle>Last Bulk Runtime Bootstrap</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto rounded-xl border border-border/70 bg-background/20 p-4 text-xs text-muted-foreground">
              {JSON.stringify(runtimeBootstrapAllMutation.data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      ) : null}

      {runtimeStatusMutation.data ? (
        <Card>
          <CardHeader>
            <CardTitle>Runtime Status</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto rounded-xl border border-border/70 bg-background/20 p-4 text-xs text-muted-foreground">
              {JSON.stringify(runtimeStatusMutation.data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
