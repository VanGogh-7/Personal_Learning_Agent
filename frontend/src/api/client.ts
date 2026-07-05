import type {
  HealthResponse,
  LongTermMemoryCreateRequest,
  LongTermMemoryListParams,
  LongTermMemoryListResponse,
  LongTermMemorySearchParams,
  LongTermMemory,
  RagQueryRequest,
  RagQueryResponse,
  StatusResponse,
} from "./types";

const API_BASE_URL = "http://127.0.0.1:8081";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      return body.detail.map((item) => item.msg ?? JSON.stringify(item)).join("; ");
    }
  } catch {
    return `Request failed with status ${response.status}`;
  }

  return `Request failed with status ${response.status}`;
}

function appendOptionalParam(params: URLSearchParams, key: string, value?: string | number): void {
  if (value !== undefined && value !== "") {
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
