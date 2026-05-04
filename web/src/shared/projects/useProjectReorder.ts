import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";

import { apiPost } from "../api/client";

type WithId = { id: number };

function moveInList<T extends WithId>(items: T[], fromId: number, toId: number): T[] {
  const from = items.findIndex((p) => p.id === fromId);
  const to = items.findIndex((p) => p.id === toId);
  if (from < 0 || to < 0 || from === to) return items;
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

export function useProjectReorder<T extends WithId>(queryKey: QueryKey) {
  const queryClient = useQueryClient();

  const reorderProjects = useMutation({
    mutationFn: (orderedProjectIds: number[]) => apiPost<{ ok: boolean }>("/api/projects/reorder", { orderedProjectIds }),
    onError: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard-top-projects"] });
      queryClient.invalidateQueries({ queryKey: ["projects", "priority-list"] });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard-top-projects"] });
      queryClient.invalidateQueries({ queryKey: ["projects", "priority-list"] });
    },
  });

  const moveProject = (fromId: number, toId: number) => {
    const current = (queryClient.getQueryData(queryKey) as T[] | undefined) ?? [];
    const next = moveInList(current, fromId, toId);
    if (next === current) return;
    queryClient.setQueryData(queryKey, next);
    reorderProjects.mutate(next.map((p) => p.id), {
      onError: () => queryClient.setQueryData(queryKey, current),
    });
  };

  return {
    moveProject,
    isReordering: reorderProjects.isPending,
  };
}
