import { useState } from "react";
import { getHealth, getStatus } from "../api/client";
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
          "Make sure the FastAPI backend is running on 127.0.0.1:8081.",
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
        <ResultBlock title="/health" value={health} />
        <ResultBlock title="/api/status" value={status} />
      </div>
    </section>
  );
}

function ResultBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="result-block">
      <h3>{title}</h3>
      <pre>{value ? JSON.stringify(value, null, 2) : "No result yet"}</pre>
    </div>
  );
}
