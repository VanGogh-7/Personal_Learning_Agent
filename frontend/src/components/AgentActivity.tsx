import { memo } from "react";
import type { AgentActivityState } from "../streaming/types";

function AgentActivityView({ activity }: { activity?: AgentActivityState }) {
  if (!activity || activity.steps.length === 0) {
    return null;
  }
  if (activity.compact) {
    const current =
      [...activity.steps].reverse().find((step) => step.status === "active") ||
      activity.steps[activity.steps.length - 1];
    return (
      <div className="agent-activity compact" aria-label="Agent Activity">
        <span className={`activity-dot ${current.status}`} aria-hidden="true" />
        <span>{current.message}</span>
      </div>
    );
  }
  return (
    <div className="agent-activity" aria-label="Agent Activity">
      <strong>Agent Activity</strong>
      <ul>
        {activity.steps.map((step) => (
          <li key={step.stage} className={step.status}>
            <span
              className={`activity-dot ${step.status}`}
              aria-hidden="true"
            />
            <span>{step.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export const AgentActivity = memo(AgentActivityView);
