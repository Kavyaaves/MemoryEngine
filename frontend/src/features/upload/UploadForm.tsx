// "Add memories" card: pick files, choose the source type, upload with a progress bar.
// Data flow: UploadForm → useUploadFiles (hooks/useUploads.ts) → uploadFiles() (api/uploads.ts) → POST /api/uploads
// The created jobs then appear in JobsList, which polls until they are processed.
import { useState } from "react";
import { CloudUpload } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Progress } from "@/components/ui/Progress";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { useUploadFiles } from "@/hooks/useUploads";
import { SOURCE_TYPES, type UploadSourceType } from "@/types/api";
import { sourceMeta } from "@/lib/sources";
import { fileKey, isJunkFile } from "./collectFiles";
import { FileDropZone } from "./FileDropZone";
import { SelectedFilesList } from "./SelectedFilesList";

export function UploadForm() {
  const [files, setFiles] = useState<File[]>([]);
  const [sourceType, setSourceType] = useState<UploadSourceType>("auto");
  const [selfName, setSelfName] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const upload = useUploadFiles();

  const addFiles = (incoming: File[]) => {
    setSuccessMessage(null);
    setFiles((current) => {
      const seenKeys = new Set(current.map(fileKey));
      const next = [...current];
      for (const file of incoming) {
        if (isJunkFile(file.name) || seenKeys.has(fileKey(file))) continue;
        seenKeys.add(fileKey(file));
        next.push(file);
      }
      return next;
    });
  };

  const startUpload = () =>
    upload.mutate(
      { files, sourceType, selfName },
      {
        onSuccess: (response) => {
          setFiles([]);
          setSuccessMessage(`Queued ${response.jobs.length} job${response.jobs.length === 1 ? "" : "s"}.`);
        },
      },
    );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add memories</CardTitle>
        <CardDescription>
          WhatsApp / Instagram exports, journals, documents, photos, audio and video. Files are processed in the
          background; duplicates are detected automatically.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <FileDropZone onFiles={addFiles} />

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="source_type">Source type</Label>
            <Select
              id="source_type"
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value as UploadSourceType)}
            >
              <option value="auto">Auto-detect</option>
              {SOURCE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {sourceMeta(type).label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="self_name">Your name in chats (optional)</Label>
            <Input
              id="self_name"
              placeholder="e.g. Priya or +91 98xxxx"
              value={selfName}
              onChange={(event) => setSelfName(event.target.value)}
            />
          </div>
        </div>

        {files.length > 0 && (
          <SelectedFilesList
            files={files}
            disabled={upload.isPending}
            onRemove={(removed) => setFiles((current) => current.filter((file) => fileKey(file) !== fileKey(removed)))}
            onClear={() => setFiles([])}
          />
        )}

        {upload.isPending && (
          <div className="flex flex-col gap-1">
            <Progress value={upload.progress} aria-label="Upload progress" />
            <span className="text-xs text-muted-foreground">Uploading… {Math.round(upload.progress * 100)}%</span>
          </div>
        )}
        {upload.isError && (
          <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {upload.error.message}
          </p>
        )}
        {successMessage && !upload.isPending && (
          <p role="status" className="text-sm text-success">
            {successMessage}
          </p>
        )}

        <div className="flex justify-end">
          <Button onClick={startUpload} disabled={files.length === 0 || upload.isPending}>
            {upload.isPending ? <Spinner /> : <CloudUpload />}
            Upload {files.length > 0 ? `${files.length} file${files.length === 1 ? "" : "s"}` : ""}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
