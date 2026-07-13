import { useEffect, useMemo, useState } from "react";
import {
  activateProviderProfile,
  createProviderProfile,
  deleteProviderProfile,
  listProviderCatalog,
  listProviderProfiles,
  reindexEmbeddingProfile,
  testProviderConnection,
  updateProviderSecretReference,
  listLongTermMemories,
  deleteLongTermMemory,
} from "../api/client";
import type {
  ProviderCatalogEntry,
  ProviderConnectionTest,
  ProviderId,
  ProviderKind,
  ProviderProfile,
  ProviderProfileInput,
  LongTermMemory,
} from "../api/types";
import {
  deleteProviderSecret,
  getProviderSecret,
  secureSecretPersistenceAvailable,
  setProviderSecret,
  unlockSecretStore,
} from "../settings/secretStore";
import type { ThemePreference } from "../settings/theme";
import type { DensityPreference } from "../settings/density";
import { getBackendBaseUrl } from "../api/config";
import { StatusPill } from "../components/ContextPanel";

type SettingsSection =
  | "appearance"
  | "agent"
  | "embedding"
  | "memory"
  | "research"
  | "storage"
  | "diagnostics";

const EMPTY_CHAT: ProviderProfileInput = {
  kind: "chat",
  name: "My Agent model",
  provider: "deepseek",
  base_url: "https://api.deepseek.com",
  model: "deepseek-chat",
  temperature: 0,
  max_output_tokens: 2000,
};

const EMPTY_EMBEDDING: ProviderProfileInput = {
  kind: "embedding",
  name: "My embedding model",
  provider: "zhipu",
  base_url: "https://open.bigmodel.cn/api/paas/v4",
  model: "embedding-3",
  embedding_dimension: 1024,
  batch_size: 16,
};

export default function SettingsPage({
  theme,
  onThemeChange,
  density = "comfortable",
  onDensityChange = () => undefined,
  onBack = () => undefined,
}: {
  theme: ThemePreference;
  onThemeChange: (theme: ThemePreference) => void;
  density?: DensityPreference;
  onDensityChange?: (density: DensityPreference) => void;
  onBack?: () => void;
}) {
  const [catalog, setCatalog] = useState<ProviderCatalogEntry[]>([]);
  const [profiles, setProfiles] = useState<ProviderProfile[]>([]);
  const [chat, setChat] = useState(EMPTY_CHAT);
  const [embedding, setEmbedding] = useState(EMPTY_EMBEDDING);
  const [vaultPassphrase, setVaultPassphrase] = useState("");
  const [vaultUnlocked, setVaultUnlocked] = useState(
    !secureSecretPersistenceAvailable(),
  );
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [replacementKeys, setReplacementKeys] = useState<
    Record<string, string>
  >({});
  const [activeSection, setActiveSection] =
    useState<SettingsSection>("appearance");
  const [memories, setMemories] = useState<LongTermMemory[]>([]);
  const [loadingMemories, setLoadingMemories] = useState(false);

  const reload = async () => {
    const [entries, stored] = await Promise.all([
      listProviderCatalog(),
      listProviderProfiles(),
    ]);
    setCatalog(entries);
    setProfiles(stored.profiles);
  };

  useEffect(() => {
    void reload().catch((reason: unknown) =>
      setError(
        reason instanceof Error ? reason.message : "Could not load settings.",
      ),
    );
  }, []);

  useEffect(() => {
    if (activeSection !== "memory") return;
    setLoadingMemories(true);
    void listLongTermMemories()
      .then((result) => setMemories(result.memories))
      .catch((reason: unknown) =>
        setError(
          reason instanceof Error
            ? reason.message
            : "Could not load saved memories.",
        ),
      )
      .finally(() => setLoadingMemories(false));
  }, [activeSection]);

  const removeMemory = async (memory: LongTermMemory) => {
    setError("");
    try {
      await deleteLongTermMemory(memory.id);
      setMemories((current) => current.filter((item) => item.id !== memory.id));
      setNotice("Saved memory deleted.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not delete saved memory.",
      );
    }
  };

  const unlock = async () => {
    setError("");
    try {
      await unlockSecretStore(vaultPassphrase);
      setVaultUnlocked(true);
      setVaultPassphrase("");
      setNotice("Secure Provider vault unlocked for this app session.");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not unlock vault.",
      );
    }
  };

  const save = async (draft: ProviderProfileInput) => {
    setError("");
    setNotice("");
    if (!vaultUnlocked) {
      setError("Unlock the secure vault before saving a Provider API key.");
      return;
    }
    const apiKey = draft.api_key?.trim() || "";
    const secretRef = `provider:${crypto.randomUUID()}`;
    try {
      if (apiKey) await setProviderSecret(secretRef, apiKey);
      const created = await createProviderProfile({
        ...draft,
        api_key: undefined,
        secret_ref: apiKey ? secretRef : null,
      });
      if (draft.kind === "chat") {
        await activateProviderProfile(created.id, apiKey || null);
        setNotice("Chat profile saved and activated for new Agent requests.");
      } else {
        setNotice(
          "Embedding profile saved. Test it, then re-index before activation.",
        );
      }
      await reload();
    } catch (reason) {
      if (apiKey) await deleteProviderSecret(secretRef).catch(() => undefined);
      setError(
        reason instanceof Error ? reason.message : "Could not save profile.",
      );
    }
  };

  const test = async (draft: ProviderProfileInput) => {
    setError("");
    setNotice("Testing Provider with a minimal request…");
    try {
      const result = await testProviderConnection(draft);
      setNotice(formatConnectionResult(result));
    } catch (reason) {
      setNotice("");
      setError(
        reason instanceof Error ? reason.message : "Connection test failed.",
      );
    }
  };

  const activate = async (profile: ProviderProfile) => {
    try {
      const secret = profile.secret_ref
        ? await getProviderSecret(profile.secret_ref)
        : null;
      await activateProviderProfile(profile.id, secret);
      await reload();
      setNotice(`${profile.name} is active for new requests.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Activation failed.");
    }
  };

  const reindex = async (profile: ProviderProfile) => {
    try {
      const secret = profile.secret_ref
        ? await getProviderSecret(profile.secret_ref)
        : null;
      setNotice("Re-embedding indexed chunks. Existing vectors are preserved…");
      await reindexEmbeddingProfile(profile.id, secret);
      await reload();
      setNotice("New embedding index is ready. Activate it when convenient.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Re-index failed.");
    }
  };

  const remove = async (profile: ProviderProfile) => {
    try {
      await deleteProviderProfile(profile.id);
      if (profile.secret_ref) await deleteProviderSecret(profile.secret_ref);
      await reload();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not delete profile.",
      );
    }
  };

  const replaceKey = async (profile: ProviderProfile) => {
    const value = replacementKeys[profile.id]?.trim();
    if (!value) return;
    try {
      const reference = profile.secret_ref ?? `provider:${crypto.randomUUID()}`;
      await setProviderSecret(reference, value);
      if (!profile.secret_ref) {
        await updateProviderSecretReference(profile.id, reference);
      }
      if (profile.kind === "chat" || profile.is_active) {
        await activateProviderProfile(profile.id, value);
      }
      setReplacementKeys((current) => ({ ...current, [profile.id]: "" }));
      await reload();
      setNotice(`${profile.name} key replaced and profile reactivated.`);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not replace API key.",
      );
    }
  };

  const removeKey = async (profile: ProviderProfile) => {
    try {
      if (profile.secret_ref) await deleteProviderSecret(profile.secret_ref);
      await updateProviderSecretReference(profile.id, null);
      await reload();
      setNotice("API key removed. The profile is no longer active.");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not remove API key.",
      );
    }
  };

  const settingsNav: Array<{ id: SettingsSection; label: string }> = [
    { id: "appearance", label: "Appearance" },
    { id: "agent", label: "Agent Model" },
    { id: "embedding", label: "Embedding Model" },
    { id: "memory", label: "Memory" },
    { id: "research", label: "Research Tools" },
    { id: "storage", label: "Storage" },
    { id: "diagnostics", label: "Diagnostics" },
  ];

  return (
    <div className="settings-shell">
      <aside className="settings-sidebar">
        <div className="settings-brand">
          <span className="brand-mark">PLA</span>
          <div>
            <strong>Settings</strong>
            <small>Workspace preferences</small>
          </div>
        </div>
        <button type="button" className="back-chat-button" onClick={onBack}>
          ← Back to Chat
        </button>
        <nav aria-label="Settings sections">
          {settingsNav.map((item) => (
            <button
              type="button"
              className={activeSection === item.id ? "active" : ""}
              aria-current={activeSection === item.id ? "page" : undefined}
              onClick={() => setActiveSection(item.id)}
              key={item.id}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="settings-sidebar-footer">
          <StatusPill tone={error ? "danger" : "success"}>
            {error ? "Attention needed" : "Desktop ready"}
          </StatusPill>
          <small>v0.1.0</small>
        </div>
      </aside>
      <main className="settings-main">
        <header className="settings-header">
          <p className="eyebrow">Personal Learning Agent</p>
          <h1>
            {settingsNav.find((item) => item.id === activeSection)?.label}
          </h1>
          <p>
            Configure the desktop workspace without exposing sensitive runtime
            details.
          </p>
        </header>
        {activeSection === "appearance" && (
          <section className="settings-card">
            <h2>Appearance</h2>
            <p>
              Choose a high-contrast theme and the workspace information
              density.
            </p>
            <div className="settings-grid">
              <label>
                Theme
                <select
                  aria-label="Theme"
                  value={theme}
                  onChange={(event) =>
                    onThemeChange(event.target.value as ThemePreference)
                  }
                >
                  <option value="system">System</option>
                  <option value="light">Light</option>
                  <option value="dark">Dark</option>
                </select>
              </label>
              <label>
                Density
                <select
                  aria-label="Density"
                  value={density}
                  onChange={(event) =>
                    onDensityChange(event.target.value as DensityPreference)
                  }
                >
                  <option value="comfortable">Comfortable</option>
                  <option value="compact">Compact</option>
                </select>
              </label>
            </div>
          </section>
        )}

        {(activeSection === "agent" || activeSection === "embedding") &&
          secureSecretPersistenceAvailable() &&
          !vaultUnlocked && (
            <section className="settings-card vault-card">
              <h2>Secure Provider Vault</h2>
              <p>The passphrase unlocks Tauri Stronghold for this session.</p>
              <input
                aria-label="Vault passphrase"
                type="password"
                autoComplete="current-password"
                value={vaultPassphrase}
                onChange={(event) => setVaultPassphrase(event.target.value)}
              />
              <button type="button" onClick={() => void unlock()}>
                Unlock vault
              </button>
            </section>
          )}
        {(activeSection === "agent" || activeSection === "embedding") &&
          !secureSecretPersistenceAvailable() && (
            <p className="settings-warning">
              Browser development mode keeps API keys in memory only. Persistent
              secret storage is available in the Tauri desktop app.
            </p>
          )}

        {activeSection === "agent" && (
          <ProviderEditor
            title="Agent Model"
            draft={chat}
            catalog={catalog}
            onChange={setChat}
            onTest={test}
            onSave={save}
          />
        )}
        {activeSection === "embedding" && (
          <ProviderEditor
            title="Embedding Model"
            draft={embedding}
            catalog={catalog}
            onChange={setEmbedding}
            onTest={test}
            onSave={save}
          />
        )}

        {(activeSection === "agent" || activeSection === "embedding") && (
          <section className="settings-card">
            <h2>
              Saved {activeSection === "agent" ? "Agent" : "embedding"} profiles
            </h2>
            <div className="profile-list">
              {profiles
                .filter(
                  (profile) =>
                    profile.kind ===
                    (activeSection === "agent" ? "chat" : "embedding"),
                )
                .map((profile) => (
                  <article key={profile.id} className="profile-row">
                    <div>
                      <strong>{profile.name}</strong>
                      <span>
                        {profile.provider} · {profile.model} ·{" "}
                        {profile.api_key_mask ?? "no key"}
                        {profile.kind === "embedding"
                          ? ` · index v${profile.config_version}`
                          : ""}
                      </span>
                      {profile.is_active && !profile.runtime_active && (
                        <span>
                          Reconnect this profile after unlocking the vault
                          because the backend restarted.
                        </span>
                      )}
                    </div>
                    <div className="profile-actions">
                      <input
                        aria-label={`Replacement API Key for ${profile.name}`}
                        type="password"
                        autoComplete="off"
                        placeholder="Replacement API key"
                        value={replacementKeys[profile.id] ?? ""}
                        onChange={(event) =>
                          setReplacementKeys((current) => ({
                            ...current,
                            [profile.id]: event.target.value,
                          }))
                        }
                      />
                      <button
                        type="button"
                        onClick={() => void replaceKey(profile)}
                      >
                        Replace key
                      </button>
                      {profile.secret_ref && (
                        <button
                          type="button"
                          onClick={() => void removeKey(profile)}
                        >
                          Remove key
                        </button>
                      )}
                      {profile.kind === "embedding" && (
                        <button
                          type="button"
                          onClick={() => void reindex(profile)}
                        >
                          Re-index
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={profile.runtime_active}
                        onClick={() => void activate(profile)}
                      >
                        {profile.runtime_active ? "Active" : "Activate"}
                      </button>
                      <button
                        type="button"
                        disabled={profile.is_active}
                        onClick={() => void remove(profile)}
                      >
                        Delete
                      </button>
                    </div>
                  </article>
                ))}
              {!profiles.some(
                (profile) =>
                  profile.kind ===
                  (activeSection === "agent" ? "chat" : "embedding"),
              ) && <p>No matching desktop Provider profiles saved yet.</p>}
            </div>
          </section>
        )}

        {activeSection === "memory" && (
          <section className="settings-card">
            <h2>Memory</h2>
            <div className="setting-summary-row">
              <div>
                <strong>Long-term memory</strong>
                <p>
                  Enabled for explicit, durable preferences. Short-term
                  conversation details remain internal.
                </p>
              </div>
              <StatusPill tone="success">Enabled</StatusPill>
            </div>
            <p className="settings-warning">
              Memory enablement follows the existing backend policy; this UI
              does not expose short-term memory internals.
            </p>
            <div className="memory-list" aria-label="Saved memories">
              {loadingMemories ? (
                <p>Loading saved memories…</p>
              ) : memories.length ? (
                memories.map((memory) => (
                  <article className="memory-row" key={memory.id}>
                    <div>
                      <strong>{memory.content}</strong>
                      <span>
                        {memory.memory_type} · importance {memory.importance}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void removeMemory(memory)}
                    >
                      Delete
                    </button>
                  </article>
                ))
              ) : (
                <p>No saved long-term memories.</p>
              )}
            </div>
          </section>
        )}

        {activeSection === "research" && (
          <section className="settings-card">
            <h2>Research Tools</h2>
            <p>
              Only audited backend tools are available. Arbitrary MCP
              installation is disabled.
            </p>
            <div className="tool-status-list">
              {[
                "Tavily Search",
                "Brave Search",
                "Safe Fetch",
                "Academic Search",
              ].map((tool) => (
                <div className="setting-summary-row" key={tool}>
                  <div>
                    <strong>{tool}</strong>
                    <p>Managed by backend configuration</p>
                  </div>
                  <StatusPill>Backend managed</StatusPill>
                </div>
              ))}
            </div>
          </section>
        )}

        {activeSection === "storage" && (
          <section className="settings-card">
            <h2>Storage</h2>
            <div className="settings-facts">
              <div>
                <span>Managed PDF location</span>
                <strong>Application-managed storage</strong>
              </div>
              <div>
                <span>Database</span>
                <strong>Backend managed</strong>
              </div>
              <div>
                <span>Embedding index</span>
                <strong>
                  {profiles.find(
                    (profile) =>
                      profile.kind === "embedding" && profile.is_active,
                  )?.model || "No active profile reported"}
                </strong>
              </div>
            </div>
            <p className="settings-warning">
              Absolute paths are intentionally hidden. Temporary-file cleanup
              remains controlled by the backend.
            </p>
          </section>
        )}

        {activeSection === "diagnostics" && (
          <section className="settings-card">
            <h2>Diagnostics</h2>
            <div className="settings-facts">
              <div>
                <span>Backend</span>
                <strong>{getBackendBaseUrl()}</strong>
              </div>
              <div>
                <span>Provider profiles</span>
                <strong>{profiles.length} configured</strong>
              </div>
              <div>
                <span>MCP</span>
                <strong>Backend managed</strong>
              </div>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                void navigator.clipboard?.writeText(
                  `PLA v0.1.0\nBackend: ${getBackendBaseUrl()}\nProfiles: ${profiles.length}\nTheme: ${theme}\nDensity: ${density}`,
                )
              }
            >
              Copy safe diagnostics
            </button>
            <p className="settings-warning">
              Diagnostics never include API keys, secret references, or local
              file paths.
            </p>
          </section>
        )}

        {notice && <p className="settings-notice">{notice}</p>}
        {error && <p className="settings-error">{error}</p>}
      </main>
    </div>
  );
}

function ProviderEditor({
  title,
  draft,
  catalog,
  onChange,
  onTest,
  onSave,
}: {
  title: string;
  draft: ProviderProfileInput;
  catalog: ProviderCatalogEntry[];
  onChange: (profile: ProviderProfileInput) => void;
  onTest: (profile: ProviderProfileInput) => Promise<void>;
  onSave: (profile: ProviderProfileInput) => Promise<void>;
}) {
  const entries = useMemo(
    () =>
      catalog.filter((entry) =>
        draft.kind === "chat"
          ? entry.capabilities.chat
          : entry.capabilities.embeddings,
      ),
    [catalog, draft.kind],
  );
  const update = (field: keyof ProviderProfileInput, value: unknown) =>
    onChange({ ...draft, [field]: value });
  const selected = entries.find((entry) => entry.provider === draft.provider);

  return (
    <section className="settings-card provider-editor">
      <h2>{title}</h2>
      <div className="settings-grid">
        <label>
          Profile name
          <input
            value={draft.name}
            onChange={(e) => update("name", e.target.value)}
          />
        </label>
        <label>
          Provider
          <select
            value={draft.provider}
            onChange={(event) => {
              const provider = event.target.value as ProviderId;
              const entry = entries.find((item) => item.provider === provider);
              onChange({
                ...draft,
                provider,
                base_url:
                  (draft.kind === "chat"
                    ? entry?.default_chat_base_url
                    : entry?.default_embedding_base_url) ?? "",
              });
            }}
          >
            {entries.map((entry) => (
              <option
                key={entry.provider}
                value={entry.provider}
                disabled={entry.runtime_status !== "available"}
              >
                {entry.label}
                {entry.runtime_status !== "available"
                  ? " (native adapter pending)"
                  : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          API Key
          <input
            aria-label={`${title} API Key`}
            type="password"
            autoComplete="off"
            value={draft.api_key ?? ""}
            onChange={(e) => update("api_key", e.target.value)}
            placeholder={selected?.requires_api_key ? "Required" : "Optional"}
          />
        </label>
        <label>
          Base URL
          <input
            value={draft.base_url}
            onChange={(e) => update("base_url", e.target.value)}
          />
        </label>
        <label>
          Model name
          <input
            value={draft.model}
            onChange={(e) => update("model", e.target.value)}
          />
        </label>
        {draft.kind === "chat" ? (
          <>
            <label>
              Temperature
              <input
                type="number"
                min="0"
                max="2"
                step="0.1"
                value={draft.temperature ?? 0}
                onChange={(e) => update("temperature", Number(e.target.value))}
              />
            </label>
            <label>
              Maximum output tokens
              <input
                type="number"
                min="1"
                value={draft.max_output_tokens ?? 2000}
                onChange={(e) =>
                  update("max_output_tokens", Number(e.target.value))
                }
              />
            </label>
          </>
        ) : (
          <>
            <label>
              Embedding dimension
              <input
                type="number"
                min="1"
                value={draft.embedding_dimension ?? 1024}
                onChange={(e) =>
                  update("embedding_dimension", Number(e.target.value))
                }
              />
            </label>
            <label>
              Batch size
              <input
                type="number"
                min="1"
                max="256"
                value={draft.batch_size ?? 16}
                onChange={(e) => update("batch_size", Number(e.target.value))}
              />
            </label>
          </>
        )}
      </div>
      {selected && (
        <div
          className="capability-summary"
          aria-label={`${title} capabilities`}
        >
          <strong>Capabilities</strong>
          <span>
            {[
              selected.capabilities.chat && "Chat",
              selected.capabilities.streaming && "Streaming",
              selected.capabilities.tool_calling && "Tool calling",
              selected.capabilities.structured_output && "Structured output",
              selected.capabilities.embeddings && "Embeddings",
              selected.capabilities.multimodal_input && "Multimodal input",
            ]
              .filter(Boolean)
              .join(" · ") || "No runtime capabilities reported"}
          </span>
        </div>
      )}
      <div className="settings-actions">
        <button type="button" onClick={() => void onTest(draft)}>
          Test connection
        </button>
        <button
          type="button"
          className="primary"
          onClick={() => void onSave(draft)}
        >
          Save profile
        </button>
      </div>
    </section>
  );
}

function formatConnectionResult(result: ProviderConnectionTest): string {
  if (!result.success) return result.message;
  const dimension = result.actual_embedding_dimension
    ? ` · ${result.actual_embedding_dimension} dimensions`
    : "";
  return `Connection succeeded in ${result.latency_ms.toFixed(0)} ms${dimension}.`;
}
