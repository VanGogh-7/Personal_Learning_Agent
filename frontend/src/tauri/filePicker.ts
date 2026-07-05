import { open } from "@tauri-apps/plugin-dialog";

export async function selectLocalFile(): Promise<string | null> {
  try {
    const selected = await open({
      title: "Choose learning material",
      multiple: false,
      directory: false,
      filters: [
        {
          name: "Learning material",
          extensions: ["pdf", "tex", "md", "txt"],
        },
      ],
    });

    return typeof selected === "string" ? selected : null;
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`Could not open the file picker. ${detail}`);
  }
}

export function inferFileTypeFromPath(filePath: string): string {
  const fileName = filePath.trim().split(/[\\/]/).pop() || "";
  const dotIndex = fileName.lastIndexOf(".");
  if (dotIndex <= 0 || dotIndex === fileName.length - 1) {
    return "";
  }

  const extension = fileName.slice(dotIndex + 1).toLowerCase();
  if (extension === "pdf") {
    return "pdf";
  }
  if (extension === "tex") {
    return "tex";
  }
  if (extension === "md") {
    return "md";
  }
  if (extension === "txt") {
    return "txt";
  }

  return extension;
}
