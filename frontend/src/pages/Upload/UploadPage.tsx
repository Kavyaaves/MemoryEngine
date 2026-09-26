// Upload page: add files (UploadForm), watch them being processed (JobsList), manage imported sources (SourcesList).
import { PageHeader } from "@/components/PageHeader";
import { JobsList } from "@/features/upload/JobsList";
import { SourcesList } from "@/features/upload/SourcesList";
import { UploadForm } from "@/features/upload/UploadForm";

export default function UploadPage() {
  return (
    <div className="mx-auto max-w-6xl p-4 md:p-8">
      <PageHeader title="Upload" description="Bring your chats, journals and media into your memory engine." />
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <UploadForm />
        </div>
        <div className="lg:col-span-2">
          <JobsList />
        </div>
        <div className="lg:col-span-5">
          <SourcesList />
        </div>
      </div>
    </div>
  );
}
