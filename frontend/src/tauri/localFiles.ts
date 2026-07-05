import { openPath } from "@tauri-apps/plugin-opener";

export async function openLocalFile(filePath: string): Promise<void> {
  const trimmedPath = filePath.trim();
  if (!trimmedPath) {
    throw new Error("No local file path is available for this library item.");
  }

  try {
    await openPath(trimmedPath);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`Could not open local file path "${trimmedPath}". ${detail}`);
  }
}
