// AI Lab page (PLAN §44): providers, models, routing, quotas and retrieval internals — the engine, exposed.
// Each card fetches its own data through hooks/useLab.ts; cards reading the same endpoint share one request.
import { PageHeader } from "@/components/PageHeader";
import { LabConfigCard } from "@/features/lab/LabConfigCard";
import { ModelRoutingCard } from "@/features/lab/ModelRoutingCard";
import { ProviderUsageCard } from "@/features/lab/ProviderUsageCard";
import { RetrievalComparison } from "@/features/lab/RetrievalComparison";
import { UsageSummary } from "@/features/lab/UsageSummary";
import { SentimentCard } from "@/features/sentiment/SentimentCard";

export default function AILabPage() {
  return (
    <div className="mx-auto max-w-7xl p-4 md:p-8">
      <PageHeader
        title="AI Lab"
        description="Providers, models, routing, quotas and retrieval internals — the engine, exposed."
      />
      <div className="flex flex-col gap-6">
        <UsageSummary />
        <div className="grid gap-6 xl:grid-cols-3">
          <ProviderUsageCard className="xl:col-span-2" />
          <LabConfigCard />
        </div>
        <div className="grid gap-6 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <ModelRoutingCard />
          </div>
          <SentimentCard />
        </div>
        <RetrievalComparison />
      </div>
    </div>
  );
}
