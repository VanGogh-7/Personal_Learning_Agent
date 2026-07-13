import type { LibraryItem } from "../api/types";
import type { ChatTurn } from "../chat/conversationState";
import { AgentActivity } from "./AgentActivity";
import { SourcesPanel } from "./SourcesPanel";

export type ContextPanelTab = "sources" | "activity" | "context";

export default function ContextPanel({
  open,
  tab,
  turn,
  selectedItems,
  conversationId,
  conversationTitle,
  currentModel,
  highlightedCitationId,
  onTabChange,
  onClose,
}: {
  open: boolean;
  tab: ContextPanelTab;
  turn: ChatTurn | null;
  selectedItems: LibraryItem[];
  conversationId: string | null;
  conversationTitle: string;
  currentModel: string;
  highlightedCitationId: string | null;
  onTabChange: (tab: ContextPanelTab) => void;
  onClose: () => void;
}) {
  return (
    <aside
      className={`context-panel${open ? " open" : ""}`}
      aria-label="Context panel"
      aria-hidden={!open}
    >
      <div className="context-panel-header">
        <div
          className="context-tabs"
          role="tablist"
          aria-label="Context details"
        >
          {(["sources", "activity", "context"] as ContextPanelTab[]).map(
            (value) => (
              <button
                type="button"
                role="tab"
                aria-selected={tab === value}
                className={tab === value ? "context-tab active" : "context-tab"}
                onClick={() => onTabChange(value)}
                key={value}
              >
                {value[0].toUpperCase() + value.slice(1)}
              </button>
            ),
          )}
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label="Close context panel"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      <div className="context-panel-body">
        {tab === "sources" && (
          <>
            <PanelHeading
              title="Sources"
              detail={
                turn ? "Evidence for the selected answer" : "No answer selected"
              }
            />
            {turn ? (
              <SourcesPanel
                citations={turn.citations}
                webSources={turn.webSources}
                libraryItems={selectedItems}
                expanded
                highlightedCitationId={highlightedCitationId}
                missingCitationId={highlightedCitationId}
                onExpandedChange={() => undefined}
                mode="panel"
              />
            ) : (
              <PanelEmpty>No sources are available yet.</PanelEmpty>
            )}
          </>
        )}
        {tab === "activity" && (
          <>
            <PanelHeading
              title="Agent Activity"
              detail="Public execution stages only"
            />
            {turn?.activity?.steps.length ? (
              <AgentActivity activity={{ ...turn.activity, compact: false }} />
            ) : (
              <PanelEmpty>
                No activity has been recorded for this answer.
              </PanelEmpty>
            )}
          </>
        )}
        {tab === "context" && (
          <>
            <PanelHeading
              title="Conversation Context"
              detail="Non-sensitive runtime information"
            />
            <dl className="context-facts">
              <div>
                <dt>Conversation</dt>
                <dd>{conversationTitle}</dd>
              </div>
              <div>
                <dt>Conversation ID</dt>
                <dd>
                  {conversationId
                    ? shortId(conversationId)
                    : "Created after first message"}
                </dd>
              </div>
              <div>
                <dt>Memory</dt>
                <dd>
                  <StatusPill tone="success">Enabled</StatusPill>
                </dd>
              </div>
              <div>
                <dt>Agent model</dt>
                <dd>{currentModel}</dd>
              </div>
            </dl>
            <section className="context-books">
              <h3>Selected books</h3>
              {selectedItems.length ? (
                <ul>
                  {selectedItems.map((item) => (
                    <li key={item.id}>
                      {item.title}
                      <small>{item.status}</small>
                    </li>
                  ))}
                </ul>
              ) : (
                <PanelEmpty>
                  No books selected. This conversation can still use global
                  research tools.
                </PanelEmpty>
              )}
            </section>
          </>
        )}
      </div>
    </aside>
  );
}

export function StatusPill({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  return <span className={`status-pill ${tone}`}>{children}</span>;
}

function PanelHeading({ title, detail }: { title: string; detail: string }) {
  return (
    <header className="panel-section-heading">
      <h2>{title}</h2>
      <p>{detail}</p>
    </header>
  );
}

function PanelEmpty({ children }: { children: React.ReactNode }) {
  return <p className="panel-empty">{children}</p>;
}

function shortId(value: string): string {
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-5)}` : value;
}
