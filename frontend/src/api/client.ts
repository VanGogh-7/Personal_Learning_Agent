import type {
  AgentChatRequest,
  AgentChatResponse,
  LibraryItemListParams,
  LibraryItemListResponse,
  LibraryPdfImportRequest,
  LibraryPdfImportResponse,
  ProviderCatalogEntry,
  ProviderConnectionTest,
  ProviderProfile,
  ProviderProfileInput,
  ProviderProfileList,
  LongTermMemoryList,
} from "./types";
import { getBackendBaseUrl } from "./config";
import { AgentSSEParser } from "../streaming/parser";
import type { AgentStreamEvent } from "../streaming/types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class AgentStreamInterruptedError extends Error {
  constructor(message = "The Agent stream ended before a terminal event.") {
    super(message);
    this.name = "AgentStreamInterruptedError";
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${getBackendBaseUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      `Network request failed. Make sure the FastAPI backend is running at ${getBackendBaseUrl()}.`,
    );
  }

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return parseJsonResponse<T>(response);
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      `Backend returned invalid JSON for ${response.url}.`,
      response.status,
    );
  }
}

async function extractErrorMessage(response: Response): Promise<string> {
  const fallback =
    `Request failed with status ${response.status} ${response.statusText}`.trim();

  try {
    const body = (await response.json()) as ErrorResponseBody;
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      return body.detail.map(formatValidationError).join("; ");
    }
  } catch {
    return fallback;
  }

  return fallback;
}

type ErrorResponseBody = {
  detail?: unknown;
};

type ValidationErrorBody = {
  loc?: unknown;
  msg?: unknown;
};

function formatValidationError(item: unknown): string {
  if (isValidationErrorBody(item)) {
    const location = Array.isArray(item.loc) ? item.loc.join(".") : undefined;
    const message =
      typeof item.msg === "string" ? item.msg : JSON.stringify(item);
    return location ? `${location}: ${message}` : message;
  }

  return JSON.stringify(item);
}

function isValidationErrorBody(value: unknown): value is ValidationErrorBody {
  return typeof value === "object" && value !== null;
}

function appendOptionalParam(
  params: URLSearchParams,
  key: string,
  value?: string | number,
): void {
  if (value !== undefined && value !== "" && !Number.isNaN(value)) {
    params.set(key, String(value));
  }
}

function toLibraryQueryString(params: LibraryItemListParams): string {
  const searchParams = new URLSearchParams();
  appendOptionalParam(searchParams, "keyword", params.keyword?.trim());
  appendOptionalParam(searchParams, "status", params.status?.trim());
  appendOptionalParam(searchParams, "tag", params.tag?.trim());
  appendOptionalParam(searchParams, "limit", params.limit);
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export function listLibraryItems(
  params: LibraryItemListParams = {},
): Promise<LibraryItemListResponse> {
  return requestJson<LibraryItemListResponse>(
    `/api/library/items${toLibraryQueryString(params)}`,
  );
}

export function importLibraryPdfs(
  payload: LibraryPdfImportRequest,
): Promise<LibraryPdfImportResponse> {
  return requestJson<LibraryPdfImportResponse>("/api/library/import-pdfs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function openLibraryPdf(
  libraryItemId: string,
): Promise<{ library_item_id: string; opened: boolean }> {
  return requestJson(`/api/library/items/${libraryItemId}/open-pdf`, {
    method: "POST",
  });
}

export function listProviderCatalog(): Promise<ProviderCatalogEntry[]> {
  return requestJson<ProviderCatalogEntry[]>("/api/settings/provider-catalog");
}

export function listProviderProfiles(): Promise<ProviderProfileList> {
  return requestJson<ProviderProfileList>("/api/settings/profiles");
}

export function createProviderProfile(
  profile: ProviderProfileInput,
): Promise<ProviderProfile> {
  return requestJson<ProviderProfile>("/api/settings/profiles", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

export function activateProviderProfile(
  profileId: string,
  apiKey: string | null,
): Promise<ProviderProfile> {
  return requestJson<ProviderProfile>(
    `/api/settings/profiles/${profileId}/activate`,
    { method: "POST", body: JSON.stringify({ api_key: apiKey }) },
  );
}

export function updateProviderSecretReference(
  profileId: string,
  secretRef: string | null,
): Promise<ProviderProfile> {
  return requestJson<ProviderProfile>(
    `/api/settings/profiles/${profileId}/secret`,
    { method: "PATCH", body: JSON.stringify({ secret_ref: secretRef }) },
  );
}

export function testProviderConnection(
  profile: ProviderProfileInput,
): Promise<ProviderConnectionTest> {
  return requestJson<ProviderConnectionTest>("/api/settings/test-provider", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

export function reindexEmbeddingProfile(
  profileId: string,
  apiKey: string | null,
): Promise<{ message: string }> {
  return requestJson<{ message: string }>(
    `/api/settings/profiles/${profileId}/reindex`,
    { method: "POST", body: JSON.stringify({ api_key: apiKey }) },
  );
}

export function deleteProviderProfile(profileId: string): Promise<void> {
  return requestJson<void>(`/api/settings/profiles/${profileId}`, {
    method: "DELETE",
  });
}

export function listLongTermMemories(): Promise<LongTermMemoryList> {
  return requestJson<LongTermMemoryList>("/api/memory/long-term?limit=100");
}

export function deleteLongTermMemory(memoryId: string): Promise<void> {
  return requestJson<void>(`/api/memory/long-term/${memoryId}`, {
    method: "DELETE",
  });
}

export function queryAgentChat(
  payload: AgentChatRequest,
  signal?: AbortSignal,
): Promise<AgentChatResponse> {
  return requestJson<AgentChatResponse>("/api/agent/chat", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function queryAgentChatStream(
  payload: AgentChatRequest,
  options: {
    signal: AbortSignal;
    onEvent: (event: AgentStreamEvent) => void;
  },
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${getBackendBaseUrl()}/api/agent/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: options.signal,
    });
  } catch (error) {
    if (options.signal.aborted) {
      throw error;
    }
    throw new ApiError(
      `Network request failed. Make sure the FastAPI backend is running at ${getBackendBaseUrl()}.`,
    );
  }
  if (!response.ok) {
    throw new ApiError(await extractErrorMessage(response), response.status);
  }
  if (!response.body) {
    throw new AgentStreamInterruptedError(
      "Streaming response has no readable body.",
    );
  }
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("text/event-stream")) {
    throw new AgentStreamInterruptedError(
      "Backend returned a non-SSE response for Agent streaming.",
    );
  }

  let terminal = false;
  const parser = new AgentSSEParser((event) => {
    options.onEvent(event);
    if (
      event.type === "done" ||
      event.type === "cancelled" ||
      event.type === "error"
    ) {
      terminal = true;
    }
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.feed(decoder.decode(value, { stream: true }));
    }
    parser.feed(decoder.decode());
    parser.finish();
  } finally {
    reader.releaseLock();
  }
  if (!terminal) {
    throw new AgentStreamInterruptedError();
  }
}
