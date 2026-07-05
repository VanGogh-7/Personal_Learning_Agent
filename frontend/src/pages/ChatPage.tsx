import BackendStatus from "../components/BackendStatus";
import LongTermMemoryPanel from "../components/LongTermMemoryPanel";
import RagQueryPanel from "../components/RagQueryPanel";

export default function ChatPage() {
  return (
    <div className="page-stack">
      <section className="page-intro">
        <p>
          Ask questions against indexed learning material, inspect retrieved context, and keep
          manual long-term memories close to the study flow.
        </p>
      </section>
      <RagQueryPanel />
      <LongTermMemoryPanel />
      <BackendStatus />
    </div>
  );
}
