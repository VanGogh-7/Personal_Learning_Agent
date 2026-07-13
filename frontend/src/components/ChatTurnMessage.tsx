import { memo, useRef, useState } from "react";
import type { LibraryItem } from "../api/types";
import type { ChatTurn } from "../chat/conversationState";
import { AgentActivity } from "./AgentActivity";
import { MarkdownMessage } from "./MarkdownMessage";
import { SourcesPanel } from "./SourcesPanel";

function ChatTurnMessageView({
  turn,
  libraryItems = [],
}: {
  turn: ChatTurn;
  libraryItems?: LibraryItem[];
}) {
  const status = turn.status || "completed";
  const completed = status === "completed";
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [highlightedCitationId, setHighlightedCitationId] = useState<
    string | null
  >(null);
  const turnRef = useRef<HTMLDivElement | null>(null);

  function activateCitation(citationId: string) {
    setHighlightedCitationId(citationId);
    setSourcesExpanded(true);
    window.requestAnimationFrame(() => {
      const card = [
        ...(turnRef.current?.querySelectorAll<HTMLElement>(".source-card") ||
          []),
      ].find((element) =>
        (element.dataset.citationIds || "").split(" ").includes(citationId),
      );
      card?.focus();
      card?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    });
  }

  return (
    <div className="chat-turn" ref={turnRef}>
      <div className="chat-message user-message">
        <p>{turn.question}</p>
      </div>
      <div className={`chat-message assistant-message ${status}`}>
        {!completed && <AgentActivity activity={turn.activity} />}
        {turn.answer ? (
          completed ? (
            <MarkdownMessage
              content={turn.answer}
              onCitationActivate={activateCitation}
            />
          ) : (
            <div className="streaming-answer" aria-live="polite">
              {turn.answer}
            </div>
          )
        ) : (
          <p className="stream-placeholder">Waiting for the Agent response…</p>
        )}
        {(status === "cancelled" || status === "failed") && (
          <small className={`message-status ${status}`}>
            {status === "cancelled"
              ? "Generation stopped"
              : "Answer incomplete"}
          </small>
        )}
        {completed && (
          <SourcesPanel
            citations={turn.citations}
            webSources={turn.webSources}
            libraryItems={libraryItems}
            expanded={sourcesExpanded}
            highlightedCitationId={highlightedCitationId}
            missingCitationId={highlightedCitationId}
            onExpandedChange={setSourcesExpanded}
          />
        )}
      </div>
    </div>
  );
}

export const ChatTurnMessage = memo(ChatTurnMessageView);
