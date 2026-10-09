import type { Metadata } from "next";

import { HealthStatusSection } from "@/components/health/health-status-section";

export const metadata: Metadata = { title: "Status do ambiente" };

export default function StatusPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Status</h1>
      <HealthStatusSection />
    </div>
  );
}
