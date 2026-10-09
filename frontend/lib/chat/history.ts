// Conversation history lives only in the browser session (Phase 1 contract):
// in memory plus sessionStorage, cleared on logout and when the tab closes.

import { MAX_HISTORY_MESSAGES } from "@/lib/api/chat";
import type { ChatHistoryEntry, ChatRole, Source } from "@/lib/api/types";

export type ChatMessageStatus = "streaming" | "done" | "stopped" | "error";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  status: ChatMessageStatus;
  sources?: Source[];
  refused?: boolean;
  error?: string;
  latencyMs?: number;
}

const STORAGE_KEY = "clear-helper.chat.v1";

let counter = 0;
/** Works outside secure contexts too (`crypto.randomUUID` needs HTTPS or localhost). */
export function createMessageId(): string {
  counter += 1;
  return `${Date.now().toString(36)}-${counter.toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function isMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== "object") return false;
  const m = value as Partial<ChatMessage>;
  return (
    typeof m.id === "string" &&
    (m.role === "user" || m.role === "assistant") &&
    typeof m.content === "string" &&
    typeof m.status === "string"
  );
}

export function loadChatHistory(): ChatMessage[] {
  const raw = storage()?.getItem(STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // An answer still "streaming" when the page was left can never finish.
    return parsed.filter(isMessage).map((m) => (m.status === "streaming" ? { ...m, status: "stopped" } : m));
  } catch {
    return [];
  }
}

export function saveChatHistory(messages: ChatMessage[]): void {
  const s = storage();
  if (!s) return;
  try {
    if (messages.length === 0) s.removeItem(STORAGE_KEY);
    else s.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch {
    // Quota exceeded: keep the in-memory history only.
  }
}

export function clearChatHistory(): void {
  storage()?.removeItem(STORAGE_KEY);
}

/**
 * History sent with the next question: completed messages only (stopped or failed
 * answers are left out) and at most the last 10, as required by the contract.
 */
export function buildHistory(messages: ChatMessage[]): ChatHistoryEntry[] {
  return messages
    .filter((m) => m.role === "user" || (m.status === "done" && m.content.trim() !== ""))
    .slice(-MAX_HISTORY_MESSAGES)
    .map((m) => ({ role: m.role, content: m.content }));
}
