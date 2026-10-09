import { describe, expect, it } from "vitest";

import { buildHistory, clearChatHistory, loadChatHistory, saveChatHistory, type ChatMessage } from "@/lib/chat/history";

function msg(i: number, patch: Partial<ChatMessage> = {}): ChatMessage {
  return { id: String(i), role: i % 2 === 0 ? "user" : "assistant", content: `m${i}`, status: "done", ...patch };
}

describe("histórico da conversa", () => {
  it("envia no máximo as 10 últimas mensagens concluídas", () => {
    const messages = Array.from({ length: 13 }, (_, i) => msg(i));
    const history = buildHistory(messages);
    expect(history).toHaveLength(10);
    expect(history[0]).toEqual({ role: "assistant", content: "m3" });
    expect(history[9]).toEqual({ role: "user", content: "m12" });
  });

  it("omite respostas interrompidas, com erro ou vazias", () => {
    const history = buildHistory([
      msg(0),
      msg(1, { status: "stopped" }),
      msg(2),
      msg(3, { status: "error" }),
      msg(4),
      msg(5, { content: "  " }),
    ]);
    expect(history.map((h) => h.content)).toEqual(["m0", "m2", "m4"]);
  });

  it("persiste no sessionStorage e marca respostas pendentes como interrompidas", () => {
    saveChatHistory([msg(0), msg(1, { status: "streaming" })]);
    const loaded = loadChatHistory();
    expect(loaded).toHaveLength(2);
    expect(loaded[1]?.status).toBe("stopped");

    clearChatHistory();
    expect(loadChatHistory()).toEqual([]);
  });

  it("ignora conteúdo corrompido", () => {
    sessionStorage.setItem("clear-helper.chat.v1", "{não é json");
    expect(loadChatHistory()).toEqual([]);
  });
});
