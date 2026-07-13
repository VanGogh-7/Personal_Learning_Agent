import {
  createEmptyConversationState,
  restoreConversationState,
  type ConversationState,
} from "./conversationState";

export interface ConversationEntry {
  key: string;
  title: string;
  updatedAt: string;
  state: ConversationState;
}

export interface ConversationWorkspace {
  activeKey: string;
  conversations: ConversationEntry[];
}

export interface ConversationWorkspaceRestoreResult {
  workspace: ConversationWorkspace;
  warning: string | null;
}

const STORAGE_KEY = "pla.conversationWorkspace.v2";

export function createConversationEntry(): ConversationEntry {
  return {
    key: createLocalKey(),
    title: "New conversation",
    updatedAt: new Date().toISOString(),
    state: createEmptyConversationState(),
  };
}

export function createConversationWorkspace(): ConversationWorkspace {
  const entry = createConversationEntry();
  return { activeKey: entry.key, conversations: [entry] };
}

export function restoreConversationWorkspace(): ConversationWorkspaceRestoreResult {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return migrateCurrentConversation();
    const parsed = JSON.parse(stored) as Partial<ConversationWorkspace>;
    if (!Array.isArray(parsed.conversations) || !parsed.conversations.length) {
      throw new Error("invalid conversation workspace");
    }
    const conversations = parsed.conversations
      .filter(isConversationEntry)
      .map(normalizeConversationEntry);
    if (!conversations.length) throw new Error("empty conversation workspace");
    const activeKey = conversations.some(
      (item) => item.key === parsed.activeKey,
    )
      ? (parsed.activeKey as string)
      : conversations[0].key;
    return { workspace: { activeKey, conversations }, warning: null };
  } catch {
    return {
      workspace: createConversationWorkspace(),
      warning: "The saved conversation list could not be restored.",
    };
  }
}

export function persistConversationWorkspace(
  workspace: ConversationWorkspace,
): string | null {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace));
    return null;
  } catch {
    return "Conversations could not be saved locally.";
  }
}

export function activeConversation(
  workspace: ConversationWorkspace,
): ConversationEntry {
  return (
    workspace.conversations.find((item) => item.key === workspace.activeKey) ||
    workspace.conversations[0]
  );
}

export function updateActiveConversation(
  workspace: ConversationWorkspace,
  update:
    ConversationState | ((current: ConversationState) => ConversationState),
): ConversationWorkspace {
  return updateConversationEntry(workspace, workspace.activeKey, update);
}

export function updateConversationEntry(
  workspace: ConversationWorkspace,
  key: string,
  update:
    ConversationState | ((current: ConversationState) => ConversationState),
): ConversationWorkspace {
  return {
    ...workspace,
    conversations: workspace.conversations.map((entry) => {
      if (entry.key !== key) return entry;
      const state = typeof update === "function" ? update(entry.state) : update;
      return {
        ...entry,
        state,
        title: conversationTitle(state, entry.title),
        updatedAt: new Date().toISOString(),
      };
    }),
  };
}

export function startNewConversation(
  workspace: ConversationWorkspace,
): ConversationWorkspace {
  const current = activeConversation(workspace);
  if (
    current.state.conversationId === null &&
    current.state.messages.length === 0 &&
    current.state.selectedLibraryItemIds.length === 0
  ) {
    return workspace;
  }
  const entry = createConversationEntry();
  return {
    activeKey: entry.key,
    conversations: [entry, ...workspace.conversations],
  };
}

export function selectConversation(
  workspace: ConversationWorkspace,
  key: string,
): ConversationWorkspace {
  return workspace.conversations.some((entry) => entry.key === key)
    ? { ...workspace, activeKey: key }
    : workspace;
}

function migrateCurrentConversation(): ConversationWorkspaceRestoreResult {
  const restored = restoreConversationState();
  const entry = createConversationEntry();
  entry.state = restored.state;
  entry.title = conversationTitle(restored.state, entry.title);
  return {
    workspace: { activeKey: entry.key, conversations: [entry] },
    warning: restored.warning,
  };
}

function conversationTitle(state: ConversationState, fallback: string): string {
  const question = state.messages[0]?.question.trim();
  if (!question) return fallback;
  return question.length > 42 ? `${question.slice(0, 39)}…` : question;
}

function isConversationEntry(value: unknown): value is ConversationEntry {
  if (!value || typeof value !== "object") return false;
  const entry = value as Partial<ConversationEntry>;
  return (
    typeof entry.key === "string" &&
    typeof entry.title === "string" &&
    typeof entry.updatedAt === "string" &&
    Boolean(entry.state) &&
    Array.isArray(entry.state?.messages) &&
    Array.isArray(entry.state?.selectedLibraryItemIds)
  );
}

function normalizeConversationEntry(
  entry: ConversationEntry,
): ConversationEntry {
  return {
    ...entry,
    state: {
      conversationId:
        typeof entry.state.conversationId === "string"
          ? entry.state.conversationId
          : null,
      messages: entry.state.messages.map((turn) =>
        turn.status &&
        ["pending", "streaming", "persisting"].includes(turn.status)
          ? { ...turn, status: "failed" }
          : turn,
      ),
      selectedLibraryItemIds: [
        ...new Set(
          entry.state.selectedLibraryItemIds.filter(
            (value): value is string => typeof value === "string",
          ),
        ),
      ],
    },
  };
}

function createLocalKey(): string {
  return (
    globalThis.crypto?.randomUUID?.() ||
    `conversation-${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
}
