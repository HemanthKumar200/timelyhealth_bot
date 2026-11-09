(function (window, document) {
  "use strict";

  const script = document.currentScript;
  const scriptUrl = new URL(script.src, window.location.href);
  const jsDir = new URL("./", scriptUrl);
  const assetRoot = new URL("../", jsDir);
  const apiBase =
    (script.dataset.apiBase || "").replace(/\/$/, "") || scriptUrl.origin;

  window.TH_CHAT_OVERRIDES = Object.assign(
    {
      apiBaseUrl: apiBase,
      chatEndpoint: "/api/chat",
      resetEndpoint: "/api/reset"
    },
    window.TH_CHAT_OVERRIDES || {}
  );

  function loadStylesheet(href) {
    if (document.querySelector(`link[href="${href}"]`)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.append(link);
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${src}"]`);
      if (existing) {
        existing.addEventListener("load", () => resolve());
        existing.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)));
        if (existing.dataset.loaded === "true") resolve();
        return;
      }
      const next = document.createElement("script");
      next.src = src;
      next.async = false;
      next.onload = () => {
        next.dataset.loaded = "true";
        resolve();
      };
      next.onerror = () => reject(new Error(`Failed to load ${src}`));
      document.head.append(next);
    });
  }

  loadStylesheet(new URL("css/widget.css", assetRoot).href);

  const files = ["config.js", "client.js", "widget.js"];
  files
    .reduce(
      (chain, file) => chain.then(() => loadScript(new URL(file, jsDir).href)),
      Promise.resolve()
    )
    .catch((error) => {
      console.error("Timely Health chat widget failed to load.", error);
    });
})(window, document);
