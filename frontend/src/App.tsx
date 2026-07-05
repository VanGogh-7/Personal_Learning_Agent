import { getBackendBaseUrl } from "./api/config";
import BackendStatus from "./components/BackendStatus";
import BookLibraryPanel from "./components/BookLibraryPanel";
import LongTermMemoryPanel from "./components/LongTermMemoryPanel";
import RagQueryPanel from "./components/RagQueryPanel";

export default function App() {
  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Stage 11</p>
          <h1>Personal Learning Agent</h1>
        </div>
        <p className="backend-note">Backend: {getBackendBaseUrl()}</p>
      </header>

      <div className="panel-stack">
        <BackendStatus />
        <BookLibraryPanel />
        <RagQueryPanel />
        <LongTermMemoryPanel />
      </div>
    </main>
  );
}
