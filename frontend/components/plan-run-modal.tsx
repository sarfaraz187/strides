"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { usePlanRun } from "@/hooks/use-plan-run";

export function PlanRunModal({ onClose }: { onClose: () => void }) {
  const t = useTranslations("dashboard");
  const planRun = usePlanRun();
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [duration, setDuration] = useState("30");
  const [notes, setNotes] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    planRun.mutate(
      {
        title,
        start_time: `${date}T${time}:00`,
        duration_minutes: Number(duration),
        notes,
      },
      { onSuccess: onClose },
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 p-4">
      <Card className="w-full max-w-sm rounded-2xl p-5">
        <div className="mb-4 text-base font-semibold text-primary">{t("planRunTitle")}</div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("planRunName")}
            <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("planRunDate")}
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("planRunTime")}
            <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("planRunDuration")}
            <Input type="number" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("planRunNotes")}
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>

          {planRun.isError && <div className="text-xs text-danger">{t("planRunError")}</div>}

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("planRunCancel")}
            </Button>
            <Button type="submit" disabled={planRun.isPending}>
              {t("planRunSubmit")}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
