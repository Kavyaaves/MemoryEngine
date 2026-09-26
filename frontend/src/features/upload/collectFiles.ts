// Helpers for the upload drop zone: read files out of a drag-and-drop (including whole folders,
// e.g. an unzipped WhatsApp export), skip OS junk files, and identify duplicates.

/** Recursively collect the files from a drop, walking into dropped folders. */
export async function filesFromDataTransfer(dataTransfer: DataTransfer): Promise<File[]> {
  const entries = Array.from(dataTransfer.items ?? [])
    .filter((item) => item.kind === "file")
    .map((item) => item.webkitGetAsEntry());

  // Browsers without the entries API: fall back to the flat file list (folders are skipped).
  if (entries.length === 0 || entries.some((entry) => entry === null)) {
    return Array.from(dataTransfer.files);
  }
  const files: File[] = [];
  await Promise.all(entries.map((entry) => collectEntry(entry as FileSystemEntry, files)));
  return files;
}

async function collectEntry(entry: FileSystemEntry, files: File[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
    if (!isJunkFile(file.name)) files.push(file);
    return;
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    // readEntries returns a folder's contents in batches; keep asking until it returns an empty batch.
    while (true) {
      const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
      if (batch.length === 0) break;
      await Promise.all(batch.map((child) => collectEntry(child, files)));
    }
  }
}

/** Files that operating systems create on their own (Finder/Explorer metadata). */
export function isJunkFile(name: string): boolean {
  return name === ".DS_Store" || name === "Thumbs.db" || name === "desktop.ini" || name.startsWith("._");
}

/** Same path, size and modification time ⇒ treat as the same file. */
export function fileKey(file: File): string {
  return `${file.webkitRelativePath || file.name}:${file.size}:${file.lastModified}`;
}
