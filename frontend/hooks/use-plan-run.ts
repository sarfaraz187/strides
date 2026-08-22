// frontend/hooks/use-plan-run.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { planRun, type PlanRunInput } from "@/lib/calendar-api";

export function usePlanRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: PlanRunInput) => planRun(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
