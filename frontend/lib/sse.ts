/**
 * Incremental Server-Sent Events parser (WHATWG HTML "event stream interpretation").
 *
 * `/chat` is a POST, so `EventSource` cannot be used: the body is read with
 * `fetch` + `ReadableStream` and each decoded chunk is pushed here. Network chunks
 * can split an event (or even a CRLF) anywhere, and one chunk can carry many events.
 */

export interface SseEvent {
  /** Event type; `"message"` when the stream does not send `event:`. */
  event: string;
  data: string;
  id: string | null;
}

export class SseParser {
  private buffer = "";
  private dataLines: string[] = [];
  private eventType = "";
  private lastEventId: string | null = null;
  private started = false;

  /** Feeds decoded text and returns every event completed by it. */
  push(chunk: string): SseEvent[] {
    if (!this.started && chunk.length > 0) {
      this.started = true;
      if (chunk.charCodeAt(0) === 0xfeff) chunk = chunk.slice(1);
    }
    this.buffer += chunk;
    const events: SseEvent[] = [];

    let start = 0;
    for (let i = 0; i < this.buffer.length; i++) {
      const ch = this.buffer[i];
      if (ch !== "\n" && ch !== "\r") continue;
      if (ch === "\r") {
        // A trailing CR may be the first half of a CRLF split across chunks.
        if (i === this.buffer.length - 1) break;
        if (this.buffer[i + 1] === "\n") {
          this.processLine(this.buffer.slice(start, i), events);
          i++;
          start = i + 1;
          continue;
        }
      }
      this.processLine(this.buffer.slice(start, i), events);
      start = i + 1;
    }
    this.buffer = this.buffer.slice(start);
    return events;
  }

  /**
   * Ends the stream. Lenient on purpose: a final event without the trailing blank
   * line is still dispatched (the spec would discard it).
   */
  flush(): SseEvent[] {
    const events: SseEvent[] = [];
    const rest = this.buffer.endsWith("\r") ? this.buffer.slice(0, -1) : this.buffer;
    this.buffer = "";
    if (rest.length > 0) this.processLine(rest, events);
    this.dispatch(events);
    return events;
  }

  private processLine(line: string, events: SseEvent[]): void {
    if (line === "") {
      this.dispatch(events);
      return;
    }
    if (line.startsWith(":")) return; // comment / keep-alive

    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    switch (field) {
      case "event":
        this.eventType = value;
        break;
      case "data":
        this.dataLines.push(value);
        break;
      case "id":
        if (!value.includes("\0")) this.lastEventId = value;
        break;
      default:
        // `retry` and unknown fields are irrelevant for a fetch-based stream.
        break;
    }
  }

  private dispatch(events: SseEvent[]): void {
    if (this.dataLines.length > 0) {
      events.push({ event: this.eventType || "message", data: this.dataLines.join("\n"), id: this.lastEventId });
    }
    this.dataLines = [];
    this.eventType = "";
  }
}
