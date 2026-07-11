import { openPath } from "@tauri-apps/plugin-opener";
import type { LibraryItem } from "../api/types";
import { isPdfLibraryItem } from "../utils/libraryFiles";

type PathOpener = (path: string) => Promise<void>;

export async function openManagedLibraryPdf(
  item: LibraryItem,
  opener: PathOpener = openPath,
): Promise<void> {
  const path = item.file_path?.trim();
  if (!path) {
    throw new Error(
      "This PDF has no managed file path. Re-import it to the Repository.",
    );
  }
  if (!isPdfLibraryItem(item) || !path.toLowerCase().endsWith(".pdf")) {
    throw new Error(
      "Only managed PDF files can be opened from the Repository.",
    );
  }

  try {
    await opener(path);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    if (/not found|no such file|does not exist/i.test(detail)) {
      throw new Error(
        "The managed PDF file no longer exists. Re-import it to continue.",
      );
    }
    throw new Error("The PDF could not be opened with the system PDF reader.");
  }
}
