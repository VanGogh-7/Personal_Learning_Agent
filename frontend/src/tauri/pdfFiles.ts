import { invoke } from "@tauri-apps/api/core";

export async function readPdfFile(filePath: string): Promise<Uint8Array> {
  const trimmedPath = filePath.trim();
  if (!trimmedPath) {
    throw new Error("No local PDF file path is available for this library item.");
  }

  try {
    const data = await invoke<number[]>("read_pdf_file", { path: trimmedPath });
    return new Uint8Array(data);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`Could not load PDF file "${trimmedPath}". ${detail}`);
  }
}
