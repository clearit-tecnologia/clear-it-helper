import { describe, expect, it } from "vitest";

import { SseParser } from "@/lib/sse";

describe("SseParser", () => {
  it("parseia vários eventos num único chunk", () => {
    const parser = new SseParser();
    const events = parser.push(
      'event: sources\ndata: {"sources":[]}\n\nevent: token\ndata: {"text":"Olá"}\n\nevent: token\ndata: {"text":" mundo"}\n\n',
    );
    expect(events).toEqual([
      { event: "sources", data: '{"sources":[]}', id: null },
      { event: "token", data: '{"text":"Olá"}', id: null },
      { event: "token", data: '{"text":" mundo"}', id: null },
    ]);
  });

  it("remonta eventos quebrados em qualquer ponto entre chunks de rede", () => {
    const raw = 'event: token\ndata: {"text":"abc"}\n\nevent: done\ndata: {"answer":"abc","refused":false}\n\n';
    // Every possible split point, including inside field names and the blank line.
    for (let cut = 1; cut < raw.length; cut++) {
      const parser = new SseParser();
      const events = [...parser.push(raw.slice(0, cut)), ...parser.push(raw.slice(cut))];
      expect(events.map((e) => e.event)).toEqual(["token", "done"]);
      expect(events[1]?.data).toBe('{"answer":"abc","refused":false}');
    }
  });

  it("aceita CRLF, inclusive com CR e LF em chunks diferentes", () => {
    const parser = new SseParser();
    const events = [
      ...parser.push("event: token\r"),
      ...parser.push('\ndata: {"text":"x"}\r\n\r'),
      ...parser.push("\n"),
    ];
    expect(events).toEqual([{ event: "token", data: '{"text":"x"}', id: null }]);
  });

  it("junta múltiplas linhas data, ignora comentários e usa 'message' por padrão", () => {
    const parser = new SseParser();
    const events = parser.push(": keep-alive\n\ndata: linha 1\ndata: linha 2\nid: 7\n\n");
    expect(events).toEqual([{ event: "message", data: "linha 1\nlinha 2", id: "7" }]);
  });

  it("remove apenas um espaço após os dois-pontos e trata campo sem valor", () => {
    const parser = new SseParser();
    expect(parser.push("data:  dois espaços\n\ndata\n\n")).toEqual([
      { event: "message", data: " dois espaços", id: null },
      { event: "message", data: "", id: null },
    ]);
  });

  it("não emite evento sem data e não vaza o tipo para o próximo evento", () => {
    const parser = new SseParser();
    expect(parser.push("event: ping\n\n")).toEqual([]);
    expect(parser.push("data: x\n\n")).toEqual([{ event: "message", data: "x", id: null }]);
  });

  it("descarta o BOM inicial", () => {
    const parser = new SseParser();
    expect(parser.push("﻿data: x\n\n")).toEqual([{ event: "message", data: "x", id: null }]);
  });

  it("flush entrega o último evento sem a linha em branco final", () => {
    const parser = new SseParser();
    expect(parser.push('event: done\ndata: {"answer":"ok"}')).toEqual([]);
    expect(parser.flush()).toEqual([{ event: "done", data: '{"answer":"ok"}', id: null }]);
  });
});
