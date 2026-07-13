import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "./SettingsPage";

const api = vi.hoisted(() => ({
  listProviderCatalog: vi.fn(),
  listProviderProfiles: vi.fn(),
  createProviderProfile: vi.fn(),
  activateProviderProfile: vi.fn(),
  testProviderConnection: vi.fn(),
  reindexEmbeddingProfile: vi.fn(),
  deleteProviderProfile: vi.fn(),
  updateProviderSecretReference: vi.fn(),
  listLongTermMemories: vi.fn(),
  deleteLongTermMemory: vi.fn(),
}));

vi.mock("../api/client", () => api);

describe("SettingsPage", () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => mock.mockReset());
    api.listProviderCatalog.mockResolvedValue([
      {
        provider: "deepseek",
        label: "DeepSeek",
        capabilities: {
          chat: true,
          streaming: true,
          tool_calling: false,
          structured_output: true,
          embeddings: false,
          multimodal_input: false,
          native_adapter: false,
        },
        requires_api_key: true,
        runtime_status: "available",
      },
      {
        provider: "zhipu",
        label: "Zhipu",
        capabilities: {
          chat: false,
          streaming: false,
          tool_calling: false,
          structured_output: false,
          embeddings: true,
          multimodal_input: false,
          native_adapter: false,
        },
        requires_api_key: true,
        runtime_status: "available",
      },
    ]);
    api.listProviderProfiles.mockResolvedValue({ profiles: [] });
    api.listLongTermMemories.mockResolvedValue({ memories: [], total: 0 });
  });

  it("renders independent model sections and changes the theme", async () => {
    const onThemeChange = vi.fn();
    render(<SettingsPage theme="system" onThemeChange={onThemeChange} />);
    await screen.findByText("Agent Model");
    expect(screen.getByText("Embedding Model")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Theme"), {
      target: { value: "dark" },
    });
    expect(onThemeChange).toHaveBeenCalledWith("dark");
  });

  it("tests a Provider without creating a conversation", async () => {
    api.testProviderConnection.mockResolvedValue({
      success: true,
      provider: "deepseek",
      model: "deepseek-chat",
      latency_ms: 12,
      capabilities: {},
      message: "Connection test succeeded.",
    });
    render(<SettingsPage theme="system" onThemeChange={vi.fn()} />);
    await screen.findByRole("button", { name: "Agent Model" });
    fireEvent.click(screen.getByRole("button", { name: "Agent Model" }));
    fireEvent.click(screen.getAllByText("Test connection")[0]);
    await waitFor(() =>
      expect(api.testProviderConnection).toHaveBeenCalledTimes(1),
    );
    expect(
      screen.getByText(/Connection succeeded in 12 ms/),
    ).toBeInTheDocument();
    expect(api.createProviderProfile).not.toHaveBeenCalled();
  });

  it("allows a persisted profile to reconnect after a backend restart", async () => {
    api.listProviderProfiles.mockResolvedValue({
      profiles: [
        {
          id: "profile-1",
          kind: "chat",
          name: "Saved chat",
          provider: "deepseek",
          base_url: "https://api.deepseek.com",
          model: "deepseek-chat",
          secret_ref: "provider:chat",
          api_key_configured: true,
          api_key_mask: "••••••••",
          temperature: 0,
          max_output_tokens: 1000,
          embedding_dimension: null,
          batch_size: null,
          extra_headers: {},
          config_version: 1,
          is_active: true,
          runtime_active: false,
        },
      ],
    });
    render(<SettingsPage theme="system" onThemeChange={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Agent Model" }));
    expect(await screen.findByText("Activate")).toBeEnabled();
    expect(screen.getByText(/backend restarted/)).toBeInTheDocument();
  });

  it("loads and deletes saved long-term memories from the existing API", async () => {
    api.listLongTermMemories.mockResolvedValue({
      total: 1,
      memories: [
        {
          id: "memory-1",
          memory_type: "semantic",
          content: "Preferred name is Van",
          importance: 4,
          status: "active",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    api.deleteLongTermMemory.mockResolvedValue(undefined);
    render(<SettingsPage theme="system" onThemeChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Memory" }));

    expect(
      await screen.findByText("Preferred name is Van"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(api.deleteLongTermMemory).toHaveBeenCalledWith("memory-1"),
    );
    expect(screen.queryByText("Preferred name is Van")).not.toBeInTheDocument();
  });
});
