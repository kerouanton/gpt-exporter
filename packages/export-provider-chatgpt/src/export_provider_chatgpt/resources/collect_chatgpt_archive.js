(async () => {
  "use strict";

  const COLLECTOR_VERSION = "asset-cache-v1";
  const LIMIT = 28;
  const OUTPUT_NAME = "chatgpt-archive-source.json";
  const FAILURE_RETRY_DELAY_MS = 30 * 24 * 60 * 60 * 1000;

  console.log(`Collector version: ${COLLECTOR_VERSION}`);
  const FILE_ID_RE = /(?:file_[0-9a-fA-F]{32}|file-[A-Za-z0-9]{20,})/g;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function decodeJwtPayload(token) {
    const parts = String(token).split(".");
    if (parts.length < 2) {
      throw new Error("The ChatGPT access token is not a valid JWT.");
    }

    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padding = "=".repeat((4 - (payload.length % 4)) % 4);
    const binary = atob(payload + padding);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    return JSON.parse(new TextDecoder("utf-8").decode(bytes));
  }

  async function loadAuthentication() {
    const response = await fetch("/api/auth/session", {
      credentials: "include",
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      throw new Error(
        `Unable to read the ChatGPT session: ${response.status} ${response.statusText}`
      );
    }

    const session = await response.json();
    const accessToken = session && session.accessToken;
    if (typeof accessToken !== "string" || !accessToken) {
      throw new Error("No accessToken was returned by /api/auth/session.");
    }

    const jwt = decodeJwtPayload(accessToken);
    const auth = jwt["https://api.openai.com/auth"] || {};
    const accountId =
      auth.chatgpt_account_id ||
      (typeof auth.chatgpt_account_user_id === "string"
        ? auth.chatgpt_account_user_id.split("__").pop()
        : null);

    if (!accountId) {
      throw new Error("Unable to determine the ChatGPT account ID from the session token.");
    }

    return { accessToken, accountId };
  }

  const authentication = await loadAuthentication();
  const ASSET_CACHE_KEY = `gpt-exporter.asset-cache.v1.${authentication.accountId}`;

  function loadAssetCache() {
    try {
      const raw = localStorage.getItem(ASSET_CACHE_KEY);
      if (!raw) return { version: 1, entries: {} };
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.version !== 1 || !parsed.entries || typeof parsed.entries !== "object") {
        return { version: 1, entries: {} };
      }
      return parsed;
    } catch (error) {
      console.warn("Unable to read asset cache; starting with an empty cache.", error);
      return { version: 1, entries: {} };
    }
  }

  function saveAssetCache(cache) {
    try {
      localStorage.setItem(ASSET_CACHE_KEY, JSON.stringify(cache));
    } catch (error) {
      console.warn("Unable to save asset cache.", error);
    }
  }

  function classifyAssetError(error) {
    const text = String(error && error.message ? error.message : error);
    if (/\b404\b/.test(text)) return "http_404";
    if (/\b403\b/.test(text)) return "http_403";
    if (/JSON download descriptor contains no URL/i.test(text)) return "descriptor_no_url";
    return "other";
  }

  function shouldSkipCachedAsset(entry, nowMs) {
    if (!entry || typeof entry !== "object") return false;
    if (entry.status === "downloaded") return true;
    if (
      entry.status === "failed" &&
      ["http_404", "descriptor_no_url"].includes(entry.failure_class)
    ) {
      const retryAfter = Number(entry.retry_after_ms || 0);
      return retryAfter > nowMs;
    }
    return false;
  }

  const assetCache = loadAssetCache();
  console.log(`Asset cache entries: ${Object.keys(assetCache.entries).length}`);

  window.gptExporterAssetCache = {
    key: ASSET_CACHE_KEY,
    stats: () => ({
      entries: Object.keys(assetCache.entries).length,
      downloaded: Object.values(assetCache.entries).filter((entry) => entry.status === "downloaded").length,
      failed: Object.values(assetCache.entries).filter((entry) => entry.status === "failed").length,
    }),
    clear: () => {
      localStorage.removeItem(ASSET_CACHE_KEY);
      console.log("gpt-exporter browser asset cache cleared.");
    },
    forget: (fileId) => {
      delete assetCache.entries[fileId];
      saveAssetCache(assetCache);
      console.log(`Forgot cached asset: ${fileId}`);
    },
  };

  function backendHeaders(targetPath, targetRoute = targetPath) {
    return {
      Accept: "application/json",
      Authorization: `Bearer ${authentication.accessToken}`,
      "ChatGPT-Account-ID": authentication.accountId,
      "X-OpenAI-Target-Path": targetPath,
      "X-OpenAI-Target-Route": targetRoute,
    };
  }

  async function fetchJson(url, targetPath, targetRoute = targetPath) {
    const response = await fetch(url, {
      credentials: "include",
      headers: backendHeaders(targetPath, targetRoute),
    });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}: ${url}`);
    }
    return response.json();
  }

  async function loadConversationList() {
    const items = [];
    const seen = new Set();
    let offset = 0;
    let expectedTotal = null;

    for (;;) {
      const parameters = new URLSearchParams({
        offset: String(offset),
        limit: String(LIMIT),
        order: "updated",
        is_archived: "false",
        is_starred: "false",
      });
      const url = `/backend-api/conversations?${parameters.toString()}`;
      const page = await fetchJson(
        url,
        "/backend-api/conversations",
        "/backend-api/conversations"
      );
      const pageItems = Array.isArray(page.items) ? page.items : [];

      if (expectedTotal === null && Number.isFinite(page.total)) {
        expectedTotal = page.total;
        console.log(`Expected conversation total: ${expectedTotal}`);
      }

      for (const item of pageItems) {
        if (item && typeof item.id === "string" && !seen.has(item.id)) {
          seen.add(item.id);
          items.push(item);
          console.log(`[${items.length}] ${item.title || item.id}`);
        }
      }

      if (pageItems.length === 0) break;
      offset += pageItems.length;
      if (expectedTotal !== null && items.length >= expectedTotal) break;
      if (pageItems.length < LIMIT) break;
    }

    return items;
  }

  function collectFileIds(value, output) {
    if (typeof value === "string") {
      for (const match of value.matchAll(FILE_ID_RE)) output.add(match[0]);
      return;
    }
    if (Array.isArray(value)) {
      for (const child of value) collectFileIds(child, output);
      return;
    }
    if (value && typeof value === "object") {
      for (const child of Object.values(value)) collectFileIds(child, output);
    }
  }

  function getImageV2References(message) {
    const metadata = message && message.metadata;
    const references = metadata && Array.isArray(metadata.content_references)
      ? metadata.content_references
      : [];

    const images = [];
    for (const reference of references) {
      if (!reference || reference.type !== "image_v2" || !Array.isArray(reference.images)) {
        continue;
      }

      for (const image of reference.images) {
        if (!image || typeof image !== "object") continue;

        const candidates = [];
        for (const candidate of [
          image.content_url,
          image.thumbnail_url,
          image.original_content_url,
        ]) {
          if (
            typeof candidate === "string" &&
            /^https?:\/\//i.test(candidate) &&
            !candidates.includes(candidate)
          ) {
            candidates.push(candidate);
          }
        }

        if (!candidates.length) continue;
        images.push({
          primary_url: candidates[0],
          candidates,
          title: typeof image.title === "string" ? image.title : null,
          attribution: typeof image.attribution === "string" ? image.attribution : null,
          source_page: typeof image.url === "string" ? image.url : null,
        });
      }
    }
    return images;
  }

  async function sha256Id(value) {
    const bytes = new TextEncoder().encode(value);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const hex = [...new Uint8Array(digest)]
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
    return `external_${hex.slice(0, 32)}`;
  }

  async function annotateExternalImages(conversation) {
    const mapping = conversation && conversation.mapping;
    if (!mapping || typeof mapping !== "object") return [];

    const unique = new Map();
    for (const node of Object.values(mapping)) {
      const message = node && node.message;
      if (!message || typeof message !== "object") continue;

      const imageRecords = getImageV2References(message);
      if (!imageRecords.length) continue;

      const metadata = message.metadata && typeof message.metadata === "object"
        ? message.metadata
        : (message.metadata = {});
      metadata._archive_external_images = [];

      for (const imageRecord of imageRecords) {
        const assetId = await sha256Id(imageRecord.primary_url);
        metadata._archive_external_images.push({
          asset_id: assetId,
          source_url: imageRecord.primary_url,
          candidates: imageRecord.candidates,
          title: imageRecord.title,
          attribution: imageRecord.attribution,
          source_page: imageRecord.source_page,
        });
        if (!unique.has(assetId)) unique.set(assetId, imageRecord);
      }
    }
    return [...unique.values()];
  }

  function findUrl(value) {
    if (typeof value === "string" && /^https?:\/\//i.test(value)) return value;
    if (Array.isArray(value)) {
      for (const child of value) {
        const found = findUrl(child);
        if (found) return found;
      }
    } else if (value && typeof value === "object") {
      for (const key of ["download_url", "downloadUrl", "signed_url", "signedUrl", "url"]) {
        const found = findUrl(value[key]);
        if (found) return found;
      }
      for (const child of Object.values(value)) {
        const found = findUrl(child);
        if (found) return found;
      }
    }
    return null;
  }

  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(reader.error);
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
      reader.readAsDataURL(blob);
    });
  }

  function filenameFromDisposition(value) {
    if (!value) return null;
    const utf8 = value.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8) {
      try {
        return decodeURIComponent(utf8[1]);
      } catch (_) {
        return utf8[1];
      }
    }
    const plain = value.match(/filename="?([^";]+)"?/i);
    return plain ? plain[1] : null;
  }

  async function downloadAsset(fileId) {
    const targetPath = `/backend-api/files/download/${fileId}`;
    const endpoint = `${targetPath}?post_id=&inline=false&download_intent=false`;
    let response = await fetch(endpoint, {
      credentials: "include",
      headers: backendHeaders(
        targetPath,
        "/backend-api/files/download/{file_id}"
      ),
    });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }

    let contentType = response.headers.get("content-type") || "application/octet-stream";
    let filename = filenameFromDisposition(response.headers.get("content-disposition"));

    if (contentType.toLowerCase().startsWith("application/json")) {
      const descriptor = await response.json();
      const resolvedUrl = findUrl(descriptor);
      if (!resolvedUrl) {
        throw new Error("JSON download descriptor contains no URL");
      }
      response = await fetch(resolvedUrl);
      if (!response.ok) {
        throw new Error(`Resolved URL: ${response.status} ${response.statusText}`);
      }
      contentType = response.headers.get("content-type") || contentType;
      filename =
        filenameFromDisposition(response.headers.get("content-disposition")) || filename;
    }

    const blob = await response.blob();
    return {
      file_id: fileId,
      status: "downloaded",
      filename,
      content_type: contentType,
      size_bytes: blob.size,
      base64: await blobToBase64(blob),
    };
  }

  const summaries = await loadConversationList();
  if (!summaries.length) {
    throw new Error("No non-archived root conversations were returned by ChatGPT.");
  }

  const conversations = [];
  const fileIds = new Set();
  const externalImageRecords = new Map();

  for (let index = 0; index < summaries.length; index += 1) {
    const summary = summaries[index];
    console.log(
      `Conversation [${index + 1}/${summaries.length}] ${summary.title || summary.id}`
    );
    const targetPath = `/backend-api/conversation/${summary.id}`;
    const conversation = await fetchJson(
      targetPath,
      targetPath,
      "/backend-api/conversation/{conversation_id}"
    );
    const foundExternalImages = await annotateExternalImages(conversation);
    for (const imageRecord of foundExternalImages) {
      const assetId = await sha256Id(imageRecord.primary_url);
      if (!externalImageRecords.has(assetId)) externalImageRecords.set(assetId, imageRecord);
    }
    conversations.push(conversation);
    collectFileIds(conversation, fileIds);
    await sleep(50);
  }

  const assets = [];
  const ids = [...fileIds].sort();
  const counters = {
    attempted: 0,
    downloaded: 0,
    failed: 0,
    skipped_downloaded: 0,
    skipped_failed: 0,
  };

  console.log(`Asset candidates: ${ids.length}`);

  for (let index = 0; index < ids.length; index += 1) {
    const fileId = ids[index];
    const cached = assetCache.entries[fileId];
    const nowMs = Date.now();

    if (shouldSkipCachedAsset(cached, nowMs)) {
      if (cached.status === "downloaded") {
        counters.skipped_downloaded += 1;
        assets.push({
          file_id: fileId,
          status: "cached_downloaded",
          filename: cached.filename || null,
          content_type: cached.content_type || null,
          size_bytes: cached.size_bytes || null,
          base64: null,
          cache_status: "downloaded",
          failure_class: null,
          error: null,
        });
      } else {
        counters.skipped_failed += 1;
        assets.push({
          file_id: fileId,
          status: "cached_failed",
          filename: null,
          content_type: null,
          size_bytes: null,
          base64: null,
          cache_status: "failed",
          failure_class: cached.failure_class || "other",
          error: cached.error || "Previously failed asset",
        });
      }
      if ((index + 1) % 50 === 0 || index + 1 === ids.length) {
        console.log(`Assets processed: ${index + 1}/${ids.length}`);
      }
      continue;
    }

    counters.attempted += 1;
    console.log(`Asset request [${index + 1}/${ids.length}] ${fileId}`);
    try {
      const downloaded = await downloadAsset(fileId);
      assets.push(downloaded);
      counters.downloaded += 1;
      assetCache.entries[fileId] = {
        status: "downloaded",
        filename: downloaded.filename || null,
        content_type: downloaded.content_type || null,
        size_bytes: downloaded.size_bytes || null,
        updated_at: new Date().toISOString(),
        attempts: Number(cached && cached.attempts ? cached.attempts : 0) + 1,
        failure_class: null,
        error: null,
        retry_after_ms: 0,
      };
    } catch (error) {
      const failureClass = classifyAssetError(error);
      const errorText = String(error);
      counters.failed += 1;
      console.warn(`Asset failed: ${fileId}`, error);
      assets.push({
        file_id: fileId,
        status: "failed",
        filename: null,
        content_type: null,
        size_bytes: null,
        base64: null,
        failure_class: failureClass,
        error: errorText,
      });
      assetCache.entries[fileId] = {
        status: "failed",
        filename: null,
        content_type: null,
        size_bytes: null,
        updated_at: new Date().toISOString(),
        attempts: Number(cached && cached.attempts ? cached.attempts : 0) + 1,
        failure_class: failureClass,
        error: errorText,
        retry_after_ms:
          ["http_404", "descriptor_no_url"].includes(failureClass)
            ? Date.now() + FAILURE_RETRY_DELAY_MS
            : 0,
      };
    }

    if (counters.attempted % 10 === 0) saveAssetCache(assetCache);
    await sleep(50);
  }

  saveAssetCache(assetCache);

  const externalImages = [...externalImageRecords.entries()];
  for (let index = 0; index < externalImages.length; index += 1) {
    const [assetId, imageRecord] = externalImages[index];
    console.log(
      `External image queued [${index + 1}/${externalImages.length}] ` +
      `${imageRecord.title || imageRecord.primary_url}`
    );
    assets.push({
      file_id: assetId,
      status: "pending_external_download",
      filename: null,
      content_type: null,
      size_bytes: null,
      base64: null,
      source_url: imageRecord.primary_url,
      candidate_urls: imageRecord.candidates,
      source_page: imageRecord.source_page,
      title: imageRecord.title,
      attribution: imageRecord.attribution,
      kind: "external_image",
      error: null,
    });
  }

  const bundle = {
    format: "chatgpt-archive-source-v1",
    collector_version: COLLECTOR_VERSION,
    generated_at: new Date().toISOString(),
    source_origin: location.origin,
    scope: "non-archived-root-conversations",
    summaries,
    conversations,
    assets,
  };

  const blob = new Blob([JSON.stringify(bundle)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = OUTPUT_NAME;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);

  console.log(
    `Done: ${conversations.length} conversation(s), ${ids.length} asset candidate(s). ` +
      `Network attempts: ${counters.attempted}; downloaded: ${counters.downloaded}; ` +
      `failed: ${counters.failed}; cached downloads skipped: ${counters.skipped_downloaded}; ` +
      `cached failures skipped: ${counters.skipped_failed}; ` +
      `${externalImages.length} external image(s) queued for Python.`
  );
})();
