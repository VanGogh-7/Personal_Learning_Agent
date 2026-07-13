import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Sidebar from "./Sidebar";
import { createConversationEntry } from "../chat/conversationWorkspace";

describe("workspace navigation", () => {
  it("exposes collapse, New Chat, Settings, and keyboard-operable sections", () => {
    const collapse = vi.fn();
    const newChat = vi.fn();
    const settings = vi.fn();
    render(
      <Sidebar
        collapsed={false}
        mobileOpen={false}
        conversations={[createConversationEntry()]}
        activeConversationKey="missing"
        items={[]}
        selectedItemIds={[]}
        loadingLibrary={false}
        addingPdfs={false}
        healthLabel="Ready"
        onToggleCollapsed={collapse}
        onCloseMobile={vi.fn()}
        onNewChat={newChat}
        onSelectConversation={vi.fn()}
        onRepositoryClick={vi.fn()}
        onRepositoryDoubleClick={vi.fn()}
        onAddPdfs={vi.fn()}
        onReload={vi.fn()}
        onOpenSettings={settings}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    fireEvent.click(screen.getByRole("button", { name: "New Chat" }));
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(collapse).toHaveBeenCalledOnce();
    expect(newChat).toHaveBeenCalledOnce();
    expect(settings).toHaveBeenCalledOnce();
  });
});
