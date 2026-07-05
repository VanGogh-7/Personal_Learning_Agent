import { invoke } from "@tauri-apps/api/core";
import { save } from "@tauri-apps/plugin-dialog";

export interface ExportTexNoteRequest {
  title: string;
  contentLatex: string;
}

export async function exportTexNote({
  title,
  contentLatex,
}: ExportTexNoteRequest): Promise<string | null> {
  if (!contentLatex.trim()) {
    throw new Error("Cannot export an empty LaTeX note.");
  }

  let selectedPath: string | null;
  try {
    selectedPath = await save({
      title: "Export LaTeX note",
      defaultPath: sanitizeTexFilename(title),
      filters: [
        {
          name: "LaTeX",
          extensions: ["tex"],
        },
      ],
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`Could not open the save dialog. ${detail}`);
  }

  if (!selectedPath) {
    return null;
  }

  const exportPath = ensureTexExtension(selectedPath);
  try {
    return await invoke<string>("write_tex_note_file", {
      path: exportPath,
      content: contentLatex,
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`Could not export LaTeX note. ${detail}`);
  }
}

export function sanitizeTexFilename(title: string): string {
  const stem = title
    .trim()
    .toLowerCase()
    .replace(/[<>:"/\\|?*\u0000-\u001f]+/g, "")
    .replace(/[^a-z0-9._\-\s]+/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[.\-]+|[.\-]+$/g, "");

  return ensureTexExtension(stem || "untitled-note");
}

export function ensureTexExtension(filePath: string): string {
  const trimmedPath = filePath.trim();
  return trimmedPath.toLowerCase().endsWith(".tex") ? trimmedPath : `${trimmedPath}.tex`;
}
