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
} from "../api/client";
import type {
  ProviderCatalogEntry,
  ProviderConnectionTest,
  ProviderId,
  ProviderKind,
  ProviderProfile,
  ProviderProfileInput,
} from "../api/types";
import {
  deleteProviderSecret,
  getProviderSecret,
  secureSecretPersistenceAvailable,
  setProviderSecret,
  unlockSecretStore,
} from "../settings/secretStore";
import type { ThemePreference } from "../settings/theme";

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
}: {
  theme: ThemePreference;
  onThemeChange: (theme: ThemePreference) => void;
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

  return (
    <div className="settings-page">
      <section className="settings-card">
        <h2>Appearance</h2>
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
      </section>

      {secureSecretPersistenceAvailable() && !vaultUnlocked && (
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
      {!secureSecretPersistenceAvailable() && (
        <p className="settings-warning">
          Browser development mode keeps API keys in memory only. Persistent
          secret storage is available in the Tauri desktop app.
        </p>
      )}

      <ProviderEditor
        title="Agent Model"
        draft={chat}
        catalog={catalog}
        onChange={setChat}
        onTest={test}
        onSave={save}
      />
      <ProviderEditor
        title="Embedding Model"
        draft={embedding}
        catalog={catalog}
        onChange={setEmbedding}
        onTest={test}
        onSave={save}
      />

      <section className="settings-card">
        <h2>Saved profiles</h2>
        <div className="profile-list">
          {profiles.map((profile) => (
            <article key={profile.id} className="profile-row">
              <div>
                <strong>{profile.name}</strong>
                <span>
                  {profile.provider} · {profile.model} ·{" "}
                  {profile.api_key_mask ?? "no key"}
                </span>
                {profile.is_active && !profile.runtime_active && (
                  <span>
                    Reconnect this profile after unlocking the vault because the
                    backend restarted.
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
                <button type="button" onClick={() => void replaceKey(profile)}>
                  Replace key
                </button>
                {profile.secret_ref && (
                  <button type="button" onClick={() => void removeKey(profile)}>
                    Remove key
                  </button>
                )}
                {profile.kind === "embedding" && (
                  <button type="button" onClick={() => void reindex(profile)}>
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
          {!profiles.length && <p>No desktop Provider profiles saved yet.</p>}
        </div>
      </section>

      {notice && <p className="settings-notice">{notice}</p>}
      {error && <p className="settings-error">{error}</p>}
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
