// The dashed "drag & drop files or folders here" area with "Choose files" / "Choose folder" buttons.
// It only collects File objects and hands them to `onFiles`; it doesn't upload anything itself.
import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { CloudUpload, File as FileIcon, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { filesFromDataTransfer } from "./collectFiles";

export function FileDropZone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const [dragging, setDragging] = useState(false);
  // The real <input type="file"> elements are hidden; the buttons click them.
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // `webkitdirectory` makes the picker choose a whole folder. React's types don't know this
    // attribute, so it is set directly on the DOM element.
    folderInput.current?.setAttribute("webkitdirectory", "");
  }, []);

  const onDrop = async (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    onFiles(await filesFromDataTransfer(event.dataTransfer));
  };

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    onFiles(Array.from(event.target.files ?? []));
    event.target.value = ""; // allow picking the same file again later
  };

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault(); // required, otherwise the browser opens the dropped file itself
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => void onDrop(event)}
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors",
        dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50",
      )}
    >
      <CloudUpload className={cn("size-10", dragging ? "text-primary" : "text-muted-foreground")} aria-hidden />
      <div>
        <p className="font-medium">Drag & drop files or folders here</p>
        <p className="text-sm text-muted-foreground">or pick them manually</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        <Button variant="secondary" size="sm" onClick={() => fileInput.current?.click()}>
          <FileIcon /> Choose files
        </Button>
        <Button variant="secondary" size="sm" onClick={() => folderInput.current?.click()}>
          <FolderOpen /> Choose folder
        </Button>
      </div>
      <input ref={fileInput} type="file" multiple className="hidden" onChange={onPick} />
      <input ref={folderInput} type="file" multiple className="hidden" onChange={onPick} />
    </div>
  );
}
