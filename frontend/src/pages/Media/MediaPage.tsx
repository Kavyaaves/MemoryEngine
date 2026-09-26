// Media page.
//   Photos tab: the photo library — filter by name/date, write captions, ingest them (features/media/PhotoLibrary.tsx).
//   Audio / Video tabs: search → useSearch (hooks/useSearch.ts) → GET /api/search?source_type=audio|video
import { useState, type FormEvent } from "react";
import { Film, Image as ImageIcon, Mic, Search, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { MediaGrid } from "@/features/media/MediaGrid";
import { PhotoLibrary } from "@/features/media/PhotoLibrary";
import { useSearch } from "@/hooks/useSearch";
import type { MediaSourceType } from "@/types/api";

const MEDIA_TABS: Record<MediaSourceType, { label: string; icon: LucideIcon; placeholder: string }> = {
  image: { label: "Photos", icon: ImageIcon, placeholder: "" },
  audio: { label: "Audio", icon: Mic, placeholder: "voice note about the trip…" },
  video: { label: "Video", icon: Film, placeholder: "dancing at the wedding…" },
};
const MEDIA_TYPES: MediaSourceType[] = ["image", "audio", "video"];

export default function MediaPage() {
  const [mediaType, setMediaType] = useState<MediaSourceType>("image");

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-8">
      <PageHeader title="Media" description="Your photos, voice notes and videos." />

      <Tabs value={mediaType} onValueChange={(value) => setMediaType(value as MediaSourceType)} className="mb-6">
        <TabsList aria-label="Media type">
          {MEDIA_TYPES.map((type) => {
            const { label, icon: Icon } = MEDIA_TABS[type];
            return (
              <TabsTrigger key={type} value={type}>
                <Icon /> {label}
              </TabsTrigger>
            );
          })}
        </TabsList>
      </Tabs>

      {mediaType === "image" ? <PhotoLibrary /> : <MediaSearch key={mediaType} mediaType={mediaType} />}
    </div>
  );
}

const RESULT_LIMIT = 40;

/** Audio and video: search by transcript / file name. */
function MediaSearch({ mediaType }: { mediaType: MediaSourceType }) {
  const [input, setInput] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const search = useSearch(
    submittedQuery ? { q: submittedQuery, source_type: mediaType, k: RESULT_LIMIT } : null,
  );
  const tab = MEDIA_TABS[mediaType];
  const TabIcon = tab.icon;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setSubmittedQuery(input.trim());
  };

  return (
    <>
      <form onSubmit={onSubmit} className="mb-6 flex gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={tab.placeholder}
            className="memory-text pl-8"
            aria-label={`Search ${tab.label.toLowerCase()}`}
          />
        </div>
        <Button type="submit" disabled={!input.trim()}>
          {search.isFetching ? <Spinner /> : <Search />} Search
        </Button>
      </form>

      {!submittedQuery ? (
        <EmptyState
          icon={<TabIcon />}
          title={`Search your ${tab.label.toLowerCase()}`}
          description="Describe what you remember. Audio is searchable by its transcript; video by its file name for now."
        />
      ) : search.isPending ? (
        <div className="grid gap-3 md:grid-cols-2">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-32" />
          ))}
        </div>
      ) : search.isError ? (
        <ErrorState error={search.error} onRetry={() => void search.refetch()} />
      ) : search.data.results.length === 0 ? (
        <EmptyState
          icon={<TabIcon />}
          title="Nothing found"
          description={`No ${tab.label.toLowerCase()} matched “${submittedQuery}”.`}
        />
      ) : (
        <>
          <p className="mb-3 text-xs text-muted-foreground">
            {search.data.results.length} results
            {search.data.timings_ms.total !== undefined && ` · ${Math.round(search.data.timings_ms.total)} ms`}
          </p>
          <MediaGrid results={search.data.results} kind={mediaType} />
        </>
      )}
    </>
  );
}
