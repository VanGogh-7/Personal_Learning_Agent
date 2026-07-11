import type { RagCitation, WebSource } from "../api/types";
import type {
  AgentActivityState,
  AssistantMessageStatus,
} from "../streaming/types";

export interface ChatTurn {
  id: number | string;
  question: string;
  answer: string;
  status?: AssistantMessageStatus;
  citations?: RagCitation[];
  webSources?: WebSource[];
  activity?: AgentActivityState;
  serverMessageId?: string | null;
}

export interface ConversationState {
  conversationId: string | null;
  messages: ChatTurn[];
  selectedLibraryItemIds: string[];
}

export interface ConversationRestoreResult {
  state: ConversationState;
  warning: string | null;
}

const STORAGE_KEY = "pla.currentConversation.v1";

export function createEmptyConversationState(): ConversationState {
  return {
    conversationId: null,
    messages: [],
    selectedLibraryItemIds: [],
  };
}

export function toggleSelectedLibraryItem(
  state: ConversationState,
  itemId: string,
): ConversationState {
  const selected = state.selectedLibraryItemIds.includes(itemId);
  return {
    ...state,
    selectedLibraryItemIds: selected
      ? state.selectedLibraryItemIds.filter((id) => id !== itemId)
      : [...state.selectedLibraryItemIds, itemId],
  };
}

export function pruneMissingLibraryItems(
  state: ConversationState,
  availableIds: ReadonlySet<string>,
): ConversationState {
  const selectedLibraryItemIds = state.selectedLibraryItemIds.filter((id) =>
    availableIds.has(id),
  );
  return selectedLibraryItemIds.length === state.selectedLibraryItemIds.length
    ? state
    : { ...state, selectedLibraryItemIds };
}

export function restoreConversationState(): ConversationRestoreResult {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return { state: createEmptyConversationState(), warning: null };
    }
    const parsed = JSON.parse(stored) as Partial<ConversationState>;
    if (
      (parsed.conversationId !== null &&
        typeof parsed.conversationId !== "string") ||
      !Array.isArray(parsed.messages) ||
      !Array.isArray(parsed.selectedLibraryItemIds)
    ) {
      throw new Error("invalid conversation state");
    }
    return {
      state: {
        conversationId: parsed.conversationId || null,
        messages: parsed.messages.filter(isChatTurn).map(normalizeChatTurn),
        selectedLibraryItemIds: dedupeStrings(parsed.selectedLibraryItemIds),
      },
      warning: null,
    };
  } catch {
    return {
      state: createEmptyConversationState(),
      warning: "The previous conversation state could not be restored.",
    };
  }
}

export function persistConversationState(
  state: ConversationState,
): string | null {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    return null;
  } catch {
    return "The current conversation could not be saved locally.";
  }
}

function isChatTurn(value: unknown): value is ChatTurn {
  if (!value || typeof value !== "object") {
    return false;
  }
  const turn = value as Partial<ChatTurn>;
  return (
    (typeof turn.id === "number" || typeof turn.id === "string") &&
    typeof turn.question === "string" &&
    typeof turn.answer === "string"
  );
}

function normalizeChatTurn(turn: ChatTurn): ChatTurn {
  const activeStatuses: AssistantMessageStatus[] = [
    "pending",
    "streaming",
    "persisting",
  ];
  return {
    ...turn,
    status:
      turn.status && activeStatuses.includes(turn.status)
        ? "failed"
        : turn.status || "completed",
  };
}

function dedupeStrings(values: unknown[]): string[] {
  return [
    ...new Set(
      values.filter((value): value is string => typeof value === "string"),
    ),
  ];
}
