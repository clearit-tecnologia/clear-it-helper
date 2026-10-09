"use client";

import { HealthStatusPanel } from "@/components/health/health-status-panel";
import { useReadiness } from "@/hooks/use-readiness";

export function HealthStatusSection() {
  const { data, error, isLoading, isRefreshing, lastUpdated, refresh } = useReadiness();
  return (
    <HealthStatusPanel
      data={data}
      error={error}
      isLoading={isLoading}
      isRefreshing={isRefreshing}
      lastUpdated={lastUpdated}
      onRefresh={refresh}
    />
  );
}
