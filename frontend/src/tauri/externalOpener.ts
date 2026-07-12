import { openUrl } from "@tauri-apps/plugin-opener";
import { safeExternalSourceUrl } from "../sources/sourceUtils";

type UrlOpener = (url: string) => Promise<void>;

export async function openExternalSource(
  source: { url?: string | null; doi?: string | null; arxivId?: string | null },
  opener: UrlOpener = openUrl,
): Promise<string> {
  const url = safeExternalSourceUrl(source);
  if (!url) {
    throw new Error("This source has no safe HTTP or HTTPS link.");
  }
  try {
    await opener(url);
  } catch {
    throw new Error("The source could not be opened in the system browser.");
  }
  return url;
}
