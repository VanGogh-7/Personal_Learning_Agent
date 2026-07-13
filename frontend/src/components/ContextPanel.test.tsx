import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ContextPanel from "./ContextPanel";

describe("ContextPanel", () => {
  it("switches between Sources, Activity, and Context tabs", () => {
    const onTabChange = vi.fn();
    const { rerender } = render(
      <ContextPanel
        open
        tab="sources"
        turn={null}
        selectedItems={[]}
        conversationId={null}
        conversationTitle="New conversation"
        currentModel="Configured in Settings"
        highlightedCitationId={null}
        onTabChange={onTabChange}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "Context" }));
    expect(onTabChange).toHaveBeenCalledWith("context");
    rerender(
      <ContextPanel
        open
        tab="context"
        turn={null}
        selectedItems={[]}
        conversationId="conversation-a"
        conversationTitle="Research chat"
        currentModel="Configured in Settings"
        highlightedCitationId={null}
        onTabChange={onTabChange}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("Research chat")).toBeInTheDocument();
    expect(screen.getByText("Enabled")).toBeInTheDocument();
  });
});
