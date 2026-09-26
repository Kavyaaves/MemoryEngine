import { File as FileIcon, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { formatBytes } from "@/lib/format";
import { fileKey } from "./collectFiles";

interface SelectedFilesListProps {
  files: File[];
  onRemove: (file: File) => void;
  onClear: () => void;
  /** True while uploading: the list can't be changed. */
  disabled: boolean;
}

/** The files picked for upload, with their sizes and a remove button each. */
export function SelectedFilesList({ files, onRemove, onClear, disabled }: SelectedFilesListProps) {
  const totalSize = files.reduce((sum, file) => sum + file.size, 0);

  return (
    <div className="rounded-lg border">
      <div className="flex items-center justify-between border-b px-3 py-2 text-sm">
        <span>
          {files.length} file{files.length === 1 ? "" : "s"} · {formatBytes(totalSize)}
        </span>
        <Button variant="ghost" size="sm" onClick={onClear} disabled={disabled}>
          <Trash2 /> Clear
        </Button>
      </div>
      <ul className="max-h-48 overflow-y-auto text-sm">
        {files.map((file) => {
          const path = file.webkitRelativePath || file.name;
          return (
            <li key={fileKey(file)} className="flex items-center gap-2 px-3 py-1.5 odd:bg-muted/30">
              <FileIcon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1 truncate" title={path}>
                {path}
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">{formatBytes(file.size)}</span>
              <button
                type="button"
                className="cursor-pointer rounded p-0.5 text-muted-foreground hover:text-foreground disabled:cursor-not-allowed"
                aria-label={`Remove ${file.name}`}
                disabled={disabled}
                onClick={() => onRemove(file)}
              >
                <X className="size-3.5" />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
