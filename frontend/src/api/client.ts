import type {
  CreateLibraryItemPayload,
  HealthResponse,
  LibraryItem,
  LibraryItemListParams,
  LibraryItemListResponse,
  LongTermMemoryCreateRequest,
  LongTermMemory,
  LongTermMemoryListParams,
  LongTermMemoryListResponse,
  LongTermMemorySearchParams,
  RagQueryRequest,
  RagQueryResponse,
  StatusResponse,
  UpdateLibraryItemPayload,
} from "./types";
import { getBackendBaseUrl } from "./config";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
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
  } catch (error) {
    throw new ApiError(
      `Network request failed. Make sure the FastAPI backend is running at ${getBackendBaseUrl()}.`,
    );
  }

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new ApiError(message, response.status);
  }

  return parseJsonResponse<T>(response);
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(`Backend returned invalid JSON for ${response.url}.`, response.status);
  }
}

async function extractErrorMessage(response: Response): Promise<string> {
  const fallback = `Request failed with status ${response.status} ${response.statusText}`.trim();

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
  type?: unknown;
};

function formatValidationError(item: unknown): string {
  if (isValidationErrorBody(item)) {
    const location = Array.isArray(item.loc) ? item.loc.join(".") : undefined;
    const message = typeof item.msg === "string" ? item.msg : JSON.stringify(item);
    return location ? `${location}: ${message}` : message;
  }

  return JSON.stringify(item);
}

function isValidationErrorBody(value: unknown): value is ValidationErrorBody {
  return typeof value === "object" && value !== null;
}

function appendOptionalParam(params: URLSearchParams, key: string, value?: string | number): void {
  if (value !== undefined && value !== "" && !Number.isNaN(value)) {
    params.set(key, String(value));
  }
}

function toQueryString(params: LongTermMemoryListParams): string {
  const searchParams = new URLSearchParams();
  appendOptionalParam(searchParams, "memory_type", params.memory_type?.trim());
  appendOptionalParam(searchParams, "min_importance", params.min_importance);
  appendOptionalParam(searchParams, "limit", params.limit);
  const query = searchParams.toString();
  return query ? `?${query}` : "";
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

export function getHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/health");
}

export function getStatus(): Promise<StatusResponse> {
  return requestJson<StatusResponse>("/api/status");
}

export function queryRag(payload: RagQueryRequest): Promise<RagQueryResponse> {
  return requestJson<RagQueryResponse>("/api/rag/query", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createLongTermMemory(
  payload: LongTermMemoryCreateRequest,
): Promise<LongTermMemory> {
  return requestJson<LongTermMemory>("/api/memory/long-term", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listLongTermMemories(
  params: LongTermMemoryListParams,
): Promise<LongTermMemoryListResponse> {
  return requestJson<LongTermMemoryListResponse>(
    `/api/memory/long-term${toQueryString(params)}`,
  );
}

export function searchLongTermMemories(
  params: LongTermMemorySearchParams,
): Promise<LongTermMemoryListResponse> {
  const query = toQueryString(params);
  const searchParams = new URLSearchParams(query.startsWith("?") ? query.slice(1) : query);
  searchParams.set("keyword", params.keyword.trim());
  return requestJson<LongTermMemoryListResponse>(
    `/api/memory/long-term/search?${searchParams.toString()}`,
  );
}

export function createLibraryItem(payload: CreateLibraryItemPayload): Promise<LibraryItem> {
  return requestJson<LibraryItem>("/api/library/items", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listLibraryItems(
  params: Omit<LibraryItemListParams, "keyword"> = {},
): Promise<LibraryItemListResponse> {
  return requestJson<LibraryItemListResponse>(
    `/api/library/items${toLibraryQueryString(params)}`,
  );
}

export function searchLibraryItems(
  params: LibraryItemListParams,
): Promise<LibraryItemListResponse> {
  return requestJson<LibraryItemListResponse>(
    `/api/library/items/search${toLibraryQueryString(params)}`,
  );
}

export function getLibraryItem(itemId: string): Promise<LibraryItem> {
  return requestJson<LibraryItem>(`/api/library/items/${itemId}`);
}

export function updateLibraryItem(
  itemId: string,
  payload: UpdateLibraryItemPayload,
): Promise<LibraryItem> {
  return requestJson<LibraryItem>(`/api/library/items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function archiveLibraryItem(itemId: string): Promise<LibraryItem> {
  return requestJson<LibraryItem>(`/api/library/items/${itemId}`, {
    method: "DELETE",
  });
}
