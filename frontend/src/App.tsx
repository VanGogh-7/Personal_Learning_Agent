import BackendStatus from "./components/BackendStatus";
import LongTermMemoryPanel from "./components/LongTermMemoryPanel";
import RagQueryPanel from "./components/RagQueryPanel";

export default function App() {
  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Stage 8</p>
          <h1>Personal Learning Agent</h1>
        </div>
        <p className="backend-note">Backend: http://127.0.0.1:8081</p>
      </header>

      <div className="panel-stack">
        <BackendStatus />
        <RagQueryPanel />
        <LongTermMemoryPanel />
      </div>
    </main>
  );
}
