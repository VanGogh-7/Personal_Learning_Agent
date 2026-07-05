export const DEFAULT_BACKEND_URL = "http://127.0.0.1:8081";

export function getBackendBaseUrl(): string {
  return (import.meta.env.VITE_BACKEND_URL || DEFAULT_BACKEND_URL).replace(/\/+$/, "");
}
