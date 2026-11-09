(function (window) {
  "use strict";

  const defaults = {
    apiBaseUrl: "",
    chatEndpoint: "/api/chat",
    resetEndpoint: "/api/reset",
    title: "Live Chat Support",
    welcomeMessage: "Hello! Welcome to Timely Health. How can I help you?",
    placeholder: "Type your message...",
    maxMessageChars: 500,
    requestTimeoutMs: 90000,
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
    siteButtonLift: 0,
    storageKey: "th-chat-session"
  };

  window.THChat = window.THChat || {};
  window.THChat.defaults = defaults;
  window.THChat.getConfig = function getConfig() {
    return Object.assign({}, defaults, window.TH_CHAT_OVERRIDES || {});
  };
})(window);
