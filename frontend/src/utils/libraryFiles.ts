export function fileNameFromPath(filePath: string | null | undefined): string {
  const trimmed = filePath?.trim() || "";
  return trimmed.split(/[\\/]/).filter(Boolean).pop() || "";
}

export function inferFileTypeFromPath(filePath: string): string {
  const fileName = fileNameFromPath(filePath);
  const dotIndex = fileName.lastIndexOf(".");
  if (dotIndex <= 0 || dotIndex === fileName.length - 1) {
    return "";
  }

  return fileName.slice(dotIndex + 1).toLowerCase();
}

export function isPdfPath(filePath: string | null | undefined): boolean {
  return fileNameFromPath(filePath).toLowerCase().endsWith(".pdf");
}

export function isPdfLibraryItem({
  file_path,
  file_type,
}: {
  file_path?: string | null;
  file_type?: string | null;
}): boolean {
  return normalizeFileType(file_type) === "pdf" || isPdfPath(file_path);
}

export function normalizeFileType(fileType: string | null | undefined): string {
  return fileType?.trim().toLowerCase().replace(/^\./, "") || "";
}

export function pdfSupportLabel({
  file_path,
  file_type,
}: {
  file_path?: string | null;
  file_type?: string | null;
}): "PDF" | "Unsupported" {
  return isPdfLibraryItem({ file_path, file_type }) ? "PDF" : "Unsupported";
}

export function workspaceStatusLabel(status: string | null | undefined): string {
  return status === "indexed" ? "indexed" : "unindexed";
}
