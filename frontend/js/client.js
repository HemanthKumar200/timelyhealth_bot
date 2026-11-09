(function (window) {
  "use strict";

  function joinUrl(base, path) {
    const cleanBase = String(base || "").replace(/\/$/, "");
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    return `${cleanBase}${cleanPath}`;
  }

  async function readSseJson(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result = {};
    const consume = (chunk) => {
      const line = chunk.split(/\r?\n/).find((item) => item.startsWith("data:"));
      if (!line) return;
      const event = JSON.parse(line.replace(/^data:\s*/, "").trim());
      if (event.type === "done") {
        if (!result.answer) result.answer = event.answer || "";
        if (event.sources) result.sources = event.sources;
        if (event.mode) result.mode = event.mode;
      } else if (event.type === "token" && event.text) {
        result.answer = `${result.answer || ""}${event.text}`;
      } else if (event.type === "replace") {
        result.answer = event.text || "";
      } else if (event.type === "error") {
        throw new Error(event.message || "The chatbot could not process your request.");
      }
      if (event.session_id) result.session_id = event.session_id;
      if (event.sources) result.sources = event.sources;
      if (event.mode) result.mode = event.mode;
    };
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer.trim()) consume(buffer);
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split(/\r?\n\r?\n/);
      buffer = parts.pop();
      parts.forEach(consume);
    }
    return result;
  }

  async function request(url, body, timeoutMs) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json"
        },
        body: JSON.stringify(body),
        signal: controller.signal
      });
      const contentType = (response.headers.get("content-type") || "").toLowerCase();
      let data = {};
      try {
        if (contentType.includes("text/event-stream") && response.body) {
          data = await readSseJson(response);
        } else {
          data = await response.json();
        }
      } catch {
        throw new Error("The server returned an invalid response.");
      }
      if (!response.ok) {
        const detail =
          typeof data.detail === "string"
            ? data.detail
            : "The chatbot could not process your request.";
        throw new Error(detail);
      }
      return data;
    } finally {
      window.clearTimeout(timer);
    }
  }

  window.THChat = window.THChat || {};
  window.THChat.client = {
    joinUrl,
    chat(config, payload) {
      return request(
        joinUrl(config.apiBaseUrl, config.chatEndpoint),
        payload,
        config.requestTimeoutMs
      );
    },
    reset(config, sessionId) {
      return request(
        joinUrl(config.apiBaseUrl, config.resetEndpoint),
        { session_id: sessionId },
        Math.min(config.requestTimeoutMs, 15000)
      );
    }
  };
})(window);
