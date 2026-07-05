import { useState } from "react";
import { getHealth, getStatus } from "../api/client";
import { getBackendBaseUrl } from "../api/config";
import type { HealthResponse, StatusResponse } from "../api/types";

export default function BackendStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function checkBackend() {
    setLoading(true);
    setError(null);

    try {
      const [healthResult, statusResult] = await Promise.all([getHealth(), getStatus()]);
      setHealth(healthResult);
      setStatus(statusResult);
    } catch (err) {
      setHealth(null);
      setStatus(null);
      setError(
        `${err instanceof Error ? err.message : "Backend request failed"}. ` +
          `Make sure the FastAPI backend is running at ${getBackendBaseUrl()}.`,
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Backend Status</h2>
          <p>Check FastAPI health and app metadata.</p>
        </div>
        <button type="button" onClick={checkBackend} disabled={loading}>
          {loading ? "Checking..." : "Check backend"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="result-grid">
        <ResultBlock title="/health" value={health} loading={loading} />
        <ResultBlock title="/api/status" value={status} loading={loading} />
      </div>
    </section>
  );
}

function ResultBlock({
  title,
  value,
  loading,
}: {
  title: string;
  value: unknown;
  loading: boolean;
}) {
  return (
    <div className="result-block">
      <h3>{title}</h3>
      <pre>{loading ? "Checking..." : value ? JSON.stringify(value, null, 2) : "No result yet"}</pre>
    </div>
  );
}
