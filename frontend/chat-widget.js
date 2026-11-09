(() => {
  "use strict";

  if (window.__TH_CHAT_WIDGET_LOADED__) return;
  window.__TH_CHAT_WIDGET_LOADED__ = true;

  const TH_CHAT_CONFIG = {
    apiBaseUrl: "",
    chatEndpoint: "/chat",
    resetEndpoint: "/reset",

    buttonSize: 68,
    buttonIconSize: 30,
    buttonOffsetBottom: 28,
    buttonOffsetRight: 28,

    panelWidth: 410,
    panelHeight: 540,
    panelMaxHeight: "85vh",
    panelRadius: 20,
    panelOffsetBottom: 24,
    panelOffsetRight: 28,

    headerHeight: 72,
    headerTitleSize: 18,
    closeButtonSize: 36,
    messagesPadding: 16,
    messageGap: 10,
    bubbleMaxWidth: "80%",
    bubbleRadius: 16,
    bubbleFontSize: 15,
    bubbleLineHeight: 1.5,
    timestampSize: 11,

    footerHeight: 72,
    inputHeight: 44,
    inputFontSize: 16,
    sendButtonWidth: 84,
    sendButtonHeight: 44,
    inputMaxHeightMultiline: 120,

    primaryColor: "#10b981",
    headerGradient: ["#059669", "#22c55e"],
    openAnimationMs: 250,
    requestTimeoutMs: 90000,
    siteButtonLift: 0,
    maxMessageChars: 500,
    storageKey: "th-chat-session",
    welcomeMessage: "Hello! Welcome to Timely Health. How can I help you?"
  };

  const thisScript = document.currentScript;
  const scriptOrigin = (() => {
    try {
      return thisScript && thisScript.src ? new URL(thisScript.src).origin : "";
    } catch {
      return "";
    }
  })();
  const dataApiBase = ((thisScript && thisScript.dataset.apiBase) || "").replace(/\/$/, "");

  const config = {
    ...TH_CHAT_CONFIG,
    apiBaseUrl: dataApiBase || scriptOrigin || TH_CHAT_CONFIG.apiBaseUrl,
    ...(window.TH_CHAT_OVERRIDES || {})
  };

  function detectSiteButtonLift() {
    if (config.siteButtonLift) return config.siteButtonLift;
    const nodes = Array.from(document.querySelectorAll("a, button, div"));
    const found = nodes.some((node) => {
      if (node.closest(".th-chat-root")) return false;
      const style = window.getComputedStyle(node);
      if (style.position !== "fixed") return false;
      const right = parseInt(style.right, 10);
      const bottom = parseInt(style.bottom, 10);
      return right >= 0 && right <= 40 && bottom >= 0 && bottom <= 40 && node.offsetWidth >= 40;
    });
    return found ? 80 : 0;
  }

  const lift = detectSiteButtonLift();
  const cssVars = {
    "--th-btn": `${config.buttonSize}px`,
    "--th-icon": `${config.buttonIconSize}px`,
    "--th-btn-b": `${config.buttonOffsetBottom}px`,
    "--th-btn-r": `${config.buttonOffsetRight}px`,
    "--th-pw": `${config.panelWidth}px`,
    "--th-ph": `${config.panelHeight}px`,
    "--th-pmax": config.panelMaxHeight,
    "--th-pr": `${config.panelRadius}px`,
    "--th-pb": `${config.panelOffsetBottom}px`,
    "--th-pl": `${config.panelOffsetRight}px`,
    "--th-h": `${config.headerHeight}px`,
    "--th-title": `${config.headerTitleSize}px`,
    "--th-close": `${config.closeButtonSize}px`,
    "--th-pad": `${config.messagesPadding}px`,
    "--th-gap": `${config.messageGap}px`,
    "--th-bmax": config.bubbleMaxWidth,
    "--th-br": `${config.bubbleRadius}px`,
    "--th-bfont": `${config.bubbleFontSize}px`,
    "--th-lh": config.bubbleLineHeight,
    "--th-time": `${config.timestampSize}px`,
    "--th-foot": `${config.footerHeight}px`,
    "--th-ih": `${config.inputHeight}px`,
    "--th-if": `${config.inputFontSize}px`,
    "--th-sw": `${config.sendButtonWidth}px`,
    "--th-sh": `${config.sendButtonHeight}px`,
    "--th-imax": `${config.inputMaxHeightMultiline}px`,
    "--th-primary": config.primaryColor,
    "--th-grad": `linear-gradient(120deg, ${config.headerGradient[0]}, ${config.headerGradient[1]})`,
    "--th-ms": `${config.openAnimationMs}ms`,
    "--th-lift": `${lift}px`
  };

  const css = `
    .th-chat-root { ${Object.entries(cssVars).map(([k, v]) => `${k}:${v}`).join(";")} ; font-family: Inter, system-ui, Arial, sans-serif; }
    .th-chat-root * { box-sizing: border-box; }
    .th-chat-launcher {
      position: fixed; z-index: 2147483000; right: var(--th-btn-r);
      bottom: calc(var(--th-btn-b) + env(safe-area-inset-bottom) + var(--th-lift));
      width: var(--th-btn); height: var(--th-btn); border: 0; border-radius: 50%;
      display: grid; place-items: center; color: #fff; background: var(--th-grad);
      box-shadow: 0 9px 28px #04785755; cursor: pointer;
    }
    .th-chat-launcher[hidden] { display: none !important; }
    .th-chat-launcher svg { width: var(--th-icon); height: var(--th-icon); }
    .th-chat-panel {
      position: fixed; z-index: 2147483000; right: var(--th-pl);
      bottom: calc(var(--th-pb) + env(safe-area-inset-bottom) + var(--th-lift));
      width: var(--th-pw); height: min(var(--th-ph), var(--th-pmax), calc(100dvh - 40px));
      border-radius: var(--th-pr); background: #fff; overflow: hidden;
      box-shadow: 0 18px 55px rgba(17,34,51,.22); border: 1px solid #e5eee9;
      display: flex; flex-direction: column; transform-origin: bottom right;
      transition: opacity var(--th-ms), transform var(--th-ms);
    }
    .th-chat-closed { opacity: 0; transform: translateY(12px) scale(.97); pointer-events: none; }
    .th-chat-panel:not(.th-chat-closed) { opacity: 1; transform: none; }
    .th-chat-header {
      height: var(--th-h); min-height: var(--th-h); padding: 12px 16px; background: var(--th-grad);
      color: #fff; display: flex; align-items: center; justify-content: space-between;
    }
    .th-chat-heading { display: flex; align-items: center; gap: 10px; font-size: var(--th-title); font-weight: 600; }
    .th-chat-mark { width: 38px; height: 38px; border-radius: 12px; background: #ffffff28; display: grid; place-items: center; }
    .th-chat-actions { display: flex; gap: 7px; }
    .th-chat-new, .th-chat-close { border: 0; border-radius: 9px; background: #ffffff25; color: #fff; cursor: pointer; }
    .th-chat-new { padding: 8px 10px; font-size: 12px; }
    .th-chat-close { width: var(--th-close); height: var(--th-close); font-size: 22px; }
    .th-chat-new:disabled { opacity: .5; cursor: not-allowed; }
    .th-chat-messages {
      flex: 1; min-height: 0; overflow-y: auto; padding: var(--th-pad);
      background: #f5f8f6; scroll-behavior: smooth;
    }
    .th-chat-row { display: flex; margin-bottom: var(--th-gap); }
    .th-chat-user { justify-content: flex-end; }
    .th-chat-wrap { max-width: var(--th-bmax); min-width: 0; }
    .th-chat-bubble {
      background: #fff; color: #18352b; padding: 11px 14px;
      border-radius: var(--th-br) var(--th-br) var(--th-br) 4px;
      font-size: var(--th-bfont); line-height: var(--th-lh);
      overflow-wrap: anywhere; white-space: pre-wrap; box-shadow: 0 2px 7px #163b2b0c;
    }
    .th-chat-bubble p { margin: 0 0 8px; }
    .th-chat-bubble p:last-child { margin-bottom: 0; }
    .th-chat-bubble .th-chat-answer-heading { color: #145c43; font-weight: 700; }
    .th-chat-bubble ul { margin: 4px 0 8px; padding-left: 21px; }
    .th-chat-bubble li { padding-left: 2px; margin: 3px 0; }
    .th-chat-user .th-chat-bubble {
      background: var(--th-primary); color: #fff;
      border-radius: var(--th-br) var(--th-br) 4px var(--th-br);
    }
    .th-chat-time { display: block; margin-top: 4px; text-align: right; font-size: var(--th-time); color: #91a198; }
    .th-chat-bubble a, .th-chat-sources a { color: #047857; text-decoration: underline; overflow-wrap: anywhere; }
    .th-chat-user .th-chat-bubble a { color: #fff; }
    .th-chat-typing { display: flex; gap: 5px; padding: 14px; background: #fff; border-radius: 15px; width: 58px; }
    .th-chat-typing i { width: 6px; height: 6px; background: #6b9d88; border-radius: 50%; animation: th-bounce 1s infinite; }
    .th-chat-typing i:nth-child(2) { animation-delay: .15s; }
    .th-chat-typing i:nth-child(3) { animation-delay: .3s; }
    @keyframes th-bounce { 0%,60%,100% { transform: translateY(0); } 30% { transform: translateY(-5px); } }
    .th-chat-sources { font-size: 12px; margin: -5px 0 14px 5px; color: #65786e; overflow-wrap: anywhere; }
    .th-chat-sources a { margin-right: 10px; }
    .th-chat-footer {
      min-height: var(--th-foot); display: flex; align-items: flex-end; gap: 8px;
      padding: 12px; background: #fff; border-top: 1px solid #edf1ee; position: relative;
    }
    .th-chat-composer { flex: 1; min-width: 0; position: relative; }
    .th-chat-input {
      width: 100%; min-width: 0; height: var(--th-ih); max-height: var(--th-imax);
      resize: none; border: 1px solid #d8e5dd; border-radius: 22px; padding: 11px 14px;
      font-size: var(--th-if); line-height: 1.35; outline: none;
    }
    .th-chat-input:focus { border-color: #10b981; box-shadow: 0 0 0 2px #10b98122; }
    .th-chat-count { position: absolute; right: 12px; bottom: -16px; font-size: 11px; color: #7d9389; display: none; }
    .th-chat-count.th-chat-count-on { display: block; }
    .th-chat-send {
      width: var(--th-sw); height: var(--th-sh); border: 0; border-radius: 22px;
      background: var(--th-primary); color: #fff; font-weight: 600; cursor: pointer;
    }
    .th-chat-send:disabled { opacity: .5; cursor: not-allowed; }
    .th-chat-error { background: #fff3f1; color: #913c31; padding: 10px 12px; border-radius: 12px; font-size: 13px; }
    .th-chat-retry { display: block; margin-top: 5px; color: #047857; background: none; border: 0; text-decoration: underline; cursor: pointer; }
    .th-chat-jump {
      position: absolute; left: 50%; transform: translateX(-50%); bottom: calc(var(--th-foot) + 8px);
      border: 0; border-radius: 999px; background: #12352c; color: #fff; font-size: 12px;
      padding: 6px 10px; cursor: pointer; display: none; z-index: 2;
    }
    .th-chat-jump.th-chat-jump-on { display: block; }
    @media (max-width: 480px) {
      .th-chat-panel {
        left: 8px; right: 8px; bottom: calc(8px + env(safe-area-inset-bottom));
        width: auto; height: 85dvh; max-height: 85dvh; border-radius: 16px;
      }
      .th-chat-launcher { width: 60px; height: 60px; right: 18px; bottom: calc(18px + env(safe-area-inset-bottom) + var(--th-lift)); }
      .th-chat-input { font-size: 16px; }
    }
    @media (max-height: 599px) {
      .th-chat-panel { height: calc(100dvh - 40px); max-height: calc(100dvh - 40px); }
    }
    @media (prefers-reduced-motion: reduce) {
      .th-chat-panel, .th-chat-typing i { transition: none; animation: none; }
    }
  `;

  const style = document.createElement("style");
  style.textContent = css;
  document.head.append(style);

  const root = document.createElement("div");
  root.className = "th-chat-root";
  root.innerHTML = `
    <button class="th-chat-launcher" type="button" aria-label="Open chat" aria-expanded="false">
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M20 11.5a8 8 0 0 1-8 8H5l-3 2 1.5-4.5A8 8 0 1 1 20 11.5Z" stroke="currentColor" stroke-width="1.8"/>
        <path d="M8 9.5h8M8 13h5" stroke="currentColor" stroke-width="1.8"/>
      </svg>
    </button>
    <section class="th-chat-panel th-chat-closed" role="dialog" aria-label="Timely Health Live Chat" aria-hidden="true">
      <header class="th-chat-header">
        <div class="th-chat-heading">
          <span class="th-chat-mark" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M20 11.5a8 8 0 0 1-8 8H5l-3 2 1.5-4.5A8 8 0 1 1 20 11.5Z" stroke="#fff" stroke-width="1.8"/></svg>
          </span>
          Live Chat Support
        </div>
        <div class="th-chat-actions">
          <button class="th-chat-new" type="button">New chat</button>
          <button class="th-chat-close" type="button" aria-label="Close chat">×</button>
        </div>
      </header>
      <div class="th-chat-messages" aria-live="polite" aria-relevant="additions text"></div>
      <button class="th-chat-jump" type="button">Latest ↓</button>
      <form class="th-chat-footer">
        <div class="th-chat-composer">
          <textarea class="th-chat-input" maxlength="${config.maxMessageChars}" rows="1" placeholder="Type your message..." aria-label="Type your message"></textarea>
          <span class="th-chat-count" aria-live="polite"></span>
        </div>
        <button class="th-chat-send" type="submit">Send</button>
      </form>
    </section>
  `;
  document.body.append(root);

  const $ = (sel) => root.querySelector(sel);
  const launcher = $(".th-chat-launcher");
  const panel = $(".th-chat-panel");
  const messages = $(".th-chat-messages");
  const input = $(".th-chat-input");
  const sendButton = $(".th-chat-send");
  const newChatButton = $(".th-chat-new");
  const counter = $(".th-chat-count");
  const jump = $(".th-chat-jump");

  const apiUrl = (path) => `${String(config.apiBaseUrl || "").replace(/\/$/, "")}${path}`;

  function createSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return `th-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function readSession() {
    try { return sessionStorage.getItem(config.storageKey) || createSessionId(); }
    catch { return createSessionId(); }
  }
  function writeSession(id) {
    try { sessionStorage.setItem(config.storageKey, id); } catch { /* ignore */ }
  }

  let sessionId = readSession();
  writeSession(sessionId);
  let opened = false;
  let busy = false;
  let stickToBottom = true;

  function nowTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function pruneMessages() {
    while (messages.children.length > 100) messages.firstElementChild.remove();
  }

  function scrollToBottom(force) {
    if (force || stickToBottom) messages.scrollTop = messages.scrollHeight;
  }

  function addMessage(text, role) {
    const row = document.createElement("div");
    row.className = `th-chat-row ${role === "user" ? "th-chat-user" : ""}`;
    const wrap = document.createElement("div");
    wrap.className = "th-chat-wrap";
    const bubble = document.createElement("div");
    bubble.className = "th-chat-bubble";
    bubble.textContent = text;
    const time = document.createElement("time");
    time.className = "th-chat-time";
    time.textContent = nowTime();
    wrap.append(bubble, time);
    row.append(wrap);
    messages.append(row);
    pruneMessages();
    scrollToBottom();
    return bubble;
  }

  function renderRich(element, text) {
    element.replaceChildren();
    const lines = String(text || "")
      .replace(/\uFFFD(?=\s)/g, "•")
      .split(/\r?\n/);
    let list = null;

    const appendInline = (parent, value) => {
      const tokens = value.split(/(\*\*[^*]+\*\*|https?:\/\/[^\s]+)/g);
      tokens.forEach((part) => {
        if (/^\*\*[^*]+\*\*$/.test(part)) {
          const strong = document.createElement("strong");
          strong.textContent = part.slice(2, -2);
          parent.append(strong);
          return;
        }
        if (!/^https?:\/\//i.test(part)) {
          parent.append(document.createTextNode(part));
          return;
        }
        const cleanUrl = part.replace(/[),.;!?]+$/, "");
        const trailing = part.slice(cleanUrl.length);
        try {
          const url = new URL(cleanUrl);
          const link = document.createElement("a");
          link.href = url.href;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = cleanUrl;
          parent.append(link);
        } catch {
          parent.append(document.createTextNode(cleanUrl));
        }
        if (trailing) parent.append(document.createTextNode(trailing));
      });
    };

    lines.forEach((line) => {
      const trimmed = line.trim();
      const bullet = trimmed.match(/^(?:[-*•]|\uFFFD)\s+(.+)$/);
      if (bullet) {
        if (!list) {
          list = document.createElement("ul");
          element.append(list);
        }
        const item = document.createElement("li");
        appendInline(item, bullet[1]);
        list.append(item);
        return;
      }
      list = null;
      if (!trimmed) return;

      const heading = trimmed.match(
        /^(?:#{1,3}\s+)?(?:\*\*(.+?)\*\*:?\s*|([^:]{1,56}):)\s*$/
      );
      const labeled = !heading && trimmed.match(/^([^:]{1,56}):\s+(.+)$/);
      const paragraph = document.createElement("p");
      if (heading) {
        paragraph.className = "th-chat-answer-heading";
        appendInline(paragraph, heading[1] || heading[2]);
      } else if (labeled) {
        const strong = document.createElement("strong");
        strong.textContent = labeled[1];
        paragraph.append(strong, document.createTextNode(": "));
        appendInline(paragraph, labeled[2]);
      } else {
        appendInline(paragraph, trimmed.replace(/^#{1,3}\s+/, ""));
      }
      element.append(paragraph);
    });
  }

  function addSources(sources, answer) {
    if (!Array.isArray(sources) || !sources.length) return;
    const text = String(answer || "").toLowerCase();
    if (text.includes("don't have that information") || text.includes("couldn't find that detail")) return;
    const container = document.createElement("div");
    container.className = "th-chat-sources";
    container.append(document.createTextNode("Source: "));
    sources.forEach((source, index) => {
      try {
        const url = new URL(String(source));
        if (url.protocol !== "http:" && url.protocol !== "https:") return;
        const link = document.createElement("a");
        link.href = url.href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        const host = url.hostname.replace(/^www\./, "");
        const path = url.pathname.replace(/\/$/, "");
        link.textContent = path && path !== "/" ? `${host}${path}` : host;
        container.append(link);
      } catch { /* skip */ }
    });
    if (container.querySelector("a")) {
      messages.append(container);
      scrollToBottom(true);
    }
  }

  function showWelcome() {
    if (opened) return;
    opened = true;
    addMessage(config.welcomeMessage, "bot");
  }

  function openChat() {
    panel.classList.remove("th-chat-closed");
    panel.setAttribute("aria-hidden", "false");
    launcher.hidden = true;
    launcher.setAttribute("aria-expanded", "true");
    showWelcome();
    input.focus();
  }

  function closeChat() {
    panel.classList.add("th-chat-closed");
    panel.setAttribute("aria-hidden", "true");
    launcher.hidden = false;
    launcher.setAttribute("aria-expanded", "false");
    launcher.focus();
  }

  function setBusy(value) {
    busy = value;
    sendButton.disabled = value;
    input.disabled = value;
    newChatButton.disabled = value;
  }

  function addTypingIndicator() {
    const bubble = addMessage("", "bot");
    bubble.innerHTML = `<span class="th-chat-typing" aria-label="Assistant is typing"><i></i><i></i><i></i></span>`;
    return bubble;
  }

  function showError(message, question) {
    const row = document.createElement("div");
    row.className = "th-chat-row";
    const box = document.createElement("div");
    box.className = "th-chat-error";
    box.textContent = message;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "th-chat-retry";
    retry.textContent = "Retry";
    retry.addEventListener("click", () => sendMessage(question, { retry: true }));
    box.append(retry);
    row.append(box);
    messages.append(row);
    scrollToBottom(true);
  }

  function updateCounter() {
    const used = input.value.length;
    const show = used >= config.maxMessageChars - 80;
    counter.classList.toggle("th-chat-count-on", show);
    counter.textContent = `${used}/${config.maxMessageChars}`;
  }

  async function readSse(response, onEvent) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer.trim()) {
          const line = buffer.split("\n").find((item) => item.startsWith("data:"));
          if (line) {
            try { onEvent(JSON.parse(line.replace(/^data:\s*/, "").trim())); } catch { /* ignore */ }
          }
        }
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split(/\r?\n\r?\n/);
      buffer = parts.pop();
      parts.forEach((part) => {
        const line = part.split(/\r?\n/).find((item) => item.startsWith("data:"));
        if (!line) return;
        try { onEvent(JSON.parse(line.replace(/^data:\s*/, "").trim())); } catch { /* ignore */ }
      });
    }
  }

  async function sendMessage(prefill, options = {}) {
    const question = String(prefill ?? input.value).trim();
    if (!question || busy) return;
    if (question.length > config.maxMessageChars) {
      showError(`Please keep your message under ${config.maxMessageChars} characters.`, question.slice(0, config.maxMessageChars));
      return;
    }
    if (!options.retry) addMessage(question, "user");
    input.value = "";
    input.style.height = `${config.inputHeight}px`;
    updateCounter();
    setBusy(true);
    stickToBottom = true;
    const typing = addTypingIndicator();
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), config.requestTimeoutMs);
    let assembled = "";
    try {
      const response = await fetch(apiUrl(config.chatEndpoint), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ session_id: sessionId, message: question }),
        signal: controller.signal
      });
      if (!response.ok) {
        let detail = "The chatbot could not process your request.";
        try {
          const data = await response.json();
          if (typeof data.detail === "string") detail = data.detail;
        } catch { /* keep default */ }
        throw new Error(detail);
      }
      await readSse(response, (event) => {
        if (event.session_id) {
          sessionId = event.session_id;
          writeSession(sessionId);
        }
        if (event.type === "token") {
          assembled += event.text || "";
          renderRich(typing, assembled);
          scrollToBottom();
        } else if (event.type === "replace") {
          assembled = event.text || "";
          renderRich(typing, assembled);
        } else if (event.type === "done") {
          if (!assembled.trim() && event.answer) {
            assembled = event.answer;
          }
          renderRich(typing, assembled);
          addSources(event.sources, assembled);
        } else if (event.type === "error") {
          throw new Error(event.message || "The chatbot could not process your request.");
        }
      });
      if (!assembled.trim()) {
        renderRich(typing, "I don't have that information right now. You can contact the Timely Health team for help.");
      }
    } catch (error) {
      typing.closest(".th-chat-row")?.remove();
      const message = error.name === "AbortError"
        ? "The request timed out. Please try again."
        : (error.message || "I couldn't connect to the chatbot server. Please check the connection.");
      showError(message, question);
    } finally {
      window.clearTimeout(timeoutId);
      setBusy(false);
      input.focus();
    }
  }

  launcher.addEventListener("click", openChat);
  $(".th-chat-close").addEventListener("click", closeChat);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.classList.contains("th-chat-closed")) closeChat();
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, config.inputMaxHeightMultiline)}px`;
    updateCounter();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
  $(".th-chat-footer").addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage();
  });
  messages.addEventListener("scroll", () => {
    const distance = messages.scrollHeight - messages.scrollTop - messages.clientHeight;
    stickToBottom = distance < 48;
    jump.classList.toggle("th-chat-jump-on", busy && !stickToBottom);
  });
  jump.addEventListener("click", () => {
    stickToBottom = true;
    jump.classList.remove("th-chat-jump-on");
    scrollToBottom(true);
  });
  newChatButton.addEventListener("click", async () => {
    if (busy) return;
    const old = sessionId;
    sessionId = createSessionId();
    writeSession(sessionId);
    try {
      await fetch(apiUrl(config.resetEndpoint), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: old })
      });
    } catch { /* new local session still works */ }
    messages.replaceChildren();
    opened = false;
    showWelcome();
  });
})();
