const CLIENT_NAME = "pla-provider-secrets";
const memorySecrets = new Map<string, string>();

type StrongholdHandle = {
  save: () => Promise<void>;
  store: {
    insert: (key: string, value: number[]) => Promise<void>;
    get: (key: string) => Promise<Uint8Array | null>;
    remove: (key: string) => Promise<Uint8Array | null>;
  };
};

let handle: StrongholdHandle | null = null;

function isTauriRuntime(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

export function secureSecretPersistenceAvailable(): boolean {
  return isTauriRuntime();
}

export async function unlockSecretStore(passphrase: string): Promise<void> {
  if (!isTauriRuntime()) return;
  if (!passphrase) throw new Error("A vault passphrase is required.");
  const [{ Stronghold }, { appDataDir }] = await Promise.all([
    import("@tauri-apps/plugin-stronghold"),
    import("@tauri-apps/api/path"),
  ]);
  const stronghold = await Stronghold.load(
    `${await appDataDir()}/provider-secrets.hold`,
    passphrase,
  );
  let client;
  try {
    client = await stronghold.loadClient(CLIENT_NAME);
  } catch {
    client = await stronghold.createClient(CLIENT_NAME);
  }
  handle = { save: () => stronghold.save(), store: client.getStore() };
}

export async function setProviderSecret(
  reference: string,
  value: string,
): Promise<void> {
  if (!handle) {
    if (isTauriRuntime()) throw new Error("Unlock the secure vault first.");
    memorySecrets.set(reference, value);
    return;
  }
  await handle.store.insert(
    reference,
    Array.from(new TextEncoder().encode(value)),
  );
  await handle.save();
}

export async function getProviderSecret(
  reference: string,
): Promise<string | null> {
  if (!handle) return memorySecrets.get(reference) ?? null;
  const value = await handle.store.get(reference);
  return value ? new TextDecoder().decode(value) : null;
}

export async function deleteProviderSecret(reference: string): Promise<void> {
  memorySecrets.delete(reference);
  if (!handle) return;
  await handle.store.remove(reference);
  await handle.save();
}
