// A small Server-Sent Events (SSE) reader for a fetch() response body.
// The browser's EventSource can't be used: it only makes GET requests and can't send the Authorization header.
// Data flow: chatStore.send → askStream (api/ask.ts) → readServerSentEvents(response.body) → one {event, data} per message.
//
// SSE format: lines of "field: value"; a blank line ends one event. Example:
//   event: token
//   data: {"text": "Hel"}
//   <blank line>

export interface ServerSentEvent {
  event: string;
  data: string;
}

export async function* readServerSentEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ServerSentEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = ""; // text received but not yet split into lines
  let carriageReturnHeldBack = false;
  let eventName = "";
  let dataLines: string[] = [];

  try {
    while (true) {
      const { value, done } = await reader.read();
      // `stream: true` keeps a multi-byte character (e.g. Tamil) that is split across two chunks intact.
      let text = done ? decoder.decode() : decoder.decode(value, { stream: true });

      // Lines may end in "\n", "\r\n" or "\r". A chunk ending in "\r" might be the first half of "\r\n",
      // so hold that "\r" back until the next chunk arrives.
      if (carriageReturnHeldBack) text = "\r" + text;
      carriageReturnHeldBack = !done && text.endsWith("\r");
      if (carriageReturnHeldBack) text = text.slice(0, -1);
      buffer += text.replace(/\r\n?/g, "\n");
      // If the server closed the stream without a final blank line, still deliver the last event.
      if (done) buffer += "\n\n";

      let newlineIndex = buffer.indexOf("\n");
      while (newlineIndex !== -1) {
        const line = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);
        newlineIndex = buffer.indexOf("\n");

        if (line === "") {
          if (dataLines.length > 0) yield { event: eventName || "message", data: dataLines.join("\n") };
          eventName = "";
          dataLines = [];
          continue;
        }
        if (line.startsWith(":")) continue; // comment / keep-alive ping

        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        let fieldValue = colon === -1 ? "" : line.slice(colon + 1);
        if (fieldValue.startsWith(" ")) fieldValue = fieldValue.slice(1);
        if (field === "event") eventName = fieldValue;
        if (field === "data") dataLines.push(fieldValue);
        // "id" and "retry" fields are not used by this app.
      }

      if (done) return;
    }
  } finally {
    // Runs when the stream ends, the caller stops early, or the request is aborted:
    // stop downloading whatever is left.
    reader.cancel().catch(() => {});
  }
}
