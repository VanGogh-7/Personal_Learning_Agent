import { open } from "@tauri-apps/plugin-dialog";
import { inferFileTypeFromPath, isPdfPath } from "../utils/libraryFiles";

export async function selectLocalFile(): Promise<string | null> {
  try {
    const selected = await open({
      title: "Choose PDF file",
      multiple: false,
      directory: false,
      filters: [
        {
          name: "PDF files",
          extensions: ["pdf"],
        },
      ],
    });

    if (typeof selected !== "string") {
      return null;
    }
    if (!isPdfPath(selected)) {
      throw new Error("Only .pdf files are supported in the PDF Library.");
    }

    return selected;
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`Could not open the file picker. ${detail}`);
  }
}

export { inferFileTypeFromPath };
