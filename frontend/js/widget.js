(function (window, document) {
  "use strict";

  if (window.__TH_CHAT_WIDGET_LOADED__) return;
  window.__TH_CHAT_WIDGET_LOADED__ = true;

  const config = window.THChat.getConfig();

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
    "--th-lift": `${config.siteButtonLift || 0}px`
  };

  const root = document.createElement("div");
  root.className = "th-chat-root";
  Object.entries(cssVars).forEach(([key, value]) => {
    root.style.setProperty(key, value);
  });

  root.innerHTML = `
    <button class="th-chat-launcher" type="button" aria-label="Open chat" aria-expanded="false">
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M20 11.5a8 8 0 0 1-8 8H5l-3 2 1.5-4.5A8 8 0 1 1 20 11.5Z" stroke="currentColor" stroke-width="1.8"/>
        <path d="M7.5 11.5h9" stroke="currentColor" stroke-width="1.8"/>
      </svg>
    </button>
    <section class="th-chat-panel th-chat-closed" role="dialog" aria-label="Timely Health Live Chat" aria-hidden="true">
      <header class="th-chat-header">
        <div class="th-chat-heading">
          <span class="th-chat-mark">✦</span>
          <span>
            ${config.title}
            <span class="th-chat-status">Online</span>
          </span>
        </div>
        <div class="th-chat-actions">
          <button class="th-chat-new" type="button">New chat</button>
          <button class="th-chat-close" type="button" aria-label="Close chat">×</button>
        </div>
      </header>
      <div class="th-chat-messages" aria-live="polite" aria-relevant="additions text"></div>
      <form class="th-chat-footer">
        <textarea class="th-chat-input" maxlength="${config.maxMessageChars}" rows="1" placeholder="${config.placeholder}" aria-label="Type your message"></textarea>
        <button class="th-chat-send" type="submit">Send</button>
      </form>
    </section>
  `;

  document.body.append(root);

  const $ = (selector) => root.querySelector(selector);
  const launcher = $(".th-chat-launcher");
  const panel = $(".th-chat-panel");
  const messages = $(".th-chat-messages");
  const input = $(".th-chat-input");
  const sendButton = $(".th-chat-send");
  const newChatButton = $(".th-chat-new");
  const client = window.THChat.client;

  function createSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return `th-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function readSession() {
    try {
      return sessionStorage.getItem(config.storageKey) || createSessionId();
    } catch {
      return createSessionId();
    }
  }

  function writeSession(id) {
    try {
      sessionStorage.setItem(config.storageKey, id);
    } catch {
      // Keep the in-memory session if storage is blocked.
    }
  }

  let sessionId = readSession();
  writeSession(sessionId);
  let opened = false;
  let busy = false;

  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
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
    time.textContent = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit"
    });
    wrap.append(bubble, time);
    row.append(wrap);
    messages.append(row);
    while (messages.children.length > 100) {
      messages.firstElementChild.remove();
    }
    scrollToBottom();
    return bubble;
  }

  function renderAnswer(element, text) {
    element.replaceChildren();
    const urlPattern = /(https?:\/\/[^\s]+)/g;
    text.split(urlPattern).forEach((part) => {
      if (!/^https?:\/\//i.test(part)) {
        element.append(document.createTextNode(part));
        return;
      }
      const cleanUrl = part.replace(/[),.;!?]+$/, "");
      const trailing = part.slice(cleanUrl.length);
      try {
        const url = new URL(cleanUrl);
        if (url.protocol === "http:" || url.protocol === "https:") {
          const link = document.createElement("a");
          link.href = url.href;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = cleanUrl;
          element.append(link);
        } else {
          element.append(document.createTextNode(cleanUrl));
        }
      } catch {
        element.append(document.createTextNode(cleanUrl));
      }
      if (trailing) {
        element.append(document.createTextNode(trailing));
      }
    });
  }

  function addSources(sources) {
    if (!Array.isArray(sources) || sources.length === 0) return;
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
      } catch {
        // Ignore invalid source URLs.
      }
    });
    if (container.querySelector("a")) {
      messages.append(container);
      scrollToBottom();
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
    bubble.innerHTML = `
      <span class="th-chat-typing" aria-label="Assistant is typing">
        <i></i><i></i><i></i>
      </span>
    `;
    return bubble.closest(".th-chat-row");
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
    scrollToBottom();
  }

  async function sendMessage(prefill, options = {}) {
    const question = String(prefill ?? input.value).trim();
    if (!question || busy) return;
    if (question.length > config.maxMessageChars) {
      showError(
        `Please keep your message under ${config.maxMessageChars} characters.`,
        question.slice(0, config.maxMessageChars)
      );
      return;
    }
    if (!options.retry) {
      addMessage(question, "user");
    }
    input.value = "";
    input.style.height = `${config.inputHeight}px`;
    setBusy(true);
    const typingRow = addTypingIndicator();
    try {
      const data = await client.chat(config, {
        session_id: sessionId,
        message: question
      });
      if (data.session_id) {
        sessionId = data.session_id;
        writeSession(sessionId);
      }
      typingRow.remove();
      const answer = typeof data.answer === "string" ? data.answer.trim() : "";
      if (answer) {
        const answerBubble = addMessage("", "bot");
        renderAnswer(answerBubble, answer);
      } else {
        addMessage(
          "I don't have that information right now. You can contact the Timely Health team for help.",
          "bot"
        );
      }
      addSources(data.sources);
    } catch (error) {
      typingRow.remove();
      const message =
        error.name === "AbortError"
          ? "The request timed out. Please try again."
          : error.message ||
            "I couldn't connect to the chatbot server. Please check the connection.";
      showError(message, question);
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  launcher.addEventListener("click", openChat);
  $(".th-chat-close").addEventListener("click", closeChat);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.classList.contains("th-chat-closed")) {
      closeChat();
    }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, config.inputMaxHeightMultiline)}px`;
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
  newChatButton.addEventListener("click", async () => {
    if (busy) return;
    const oldSessionId = sessionId;
    sessionId = createSessionId();
    writeSession(sessionId);
    try {
      await client.reset(config, oldSessionId);
    } catch {
      // A new session ID still starts a new client conversation.
    }
    messages.replaceChildren();
    opened = false;
    showWelcome();
  });
})(window, document);
