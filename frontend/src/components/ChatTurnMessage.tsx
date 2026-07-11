import { memo } from "react";
import type { ChatTurn } from "../chat/conversationState";
import { AgentActivity } from "./AgentActivity";
import { MarkdownMessage } from "./MarkdownMessage";

function ChatTurnMessageView({ turn }: { turn: ChatTurn }) {
  const status = turn.status || "completed";
  const completed = status === "completed";
  return (
    <div className="chat-turn">
      <div className="chat-message user-message">
        <p>{turn.question}</p>
      </div>
      <div className={`chat-message assistant-message ${status}`}>
        {!completed && <AgentActivity activity={turn.activity} />}
        {turn.answer ? (
          completed ? (
            <MarkdownMessage content={turn.answer} />
          ) : (
            <div className="streaming-answer" aria-live="polite">
              {turn.answer}
            </div>
          )
        ) : (
          <p className="stream-placeholder">等待 Agent 响应…</p>
        )}
        {(status === "cancelled" || status === "failed") && (
          <small className={`message-status ${status}`}>
            {status === "cancelled" ? "已停止生成" : "回答未完成"}
          </small>
        )}
      </div>
    </div>
  );
}

export const ChatTurnMessage = memo(ChatTurnMessageView);
