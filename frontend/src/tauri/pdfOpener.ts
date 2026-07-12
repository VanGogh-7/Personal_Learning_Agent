import type { LibraryItem } from "../api/types";
import { openLibraryPdf } from "../api/client";
import { isPdfLibraryItem } from "../utils/libraryFiles";

type ManagedPdfOpener = (libraryItemId: string) => Promise<unknown>;

export async function openManagedLibraryPdf(
  item: LibraryItem,
  opener: ManagedPdfOpener = openLibraryPdf,
): Promise<void> {
  if (!item.id || !isPdfLibraryItem(item)) {
    throw new Error(
      "Only managed PDF files can be opened from the Repository.",
    );
  }

  try {
    await opener(item.id);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    if (/not found|no such file|does not exist|unavailable/i.test(detail)) {
      throw new Error(
        "The managed PDF file no longer exists. Re-import it to continue.",
      );
    }
    throw new Error("The PDF could not be opened with the system PDF reader.");
  }
}
