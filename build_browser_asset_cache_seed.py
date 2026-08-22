import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import lzma
import re
import time
from pathlib import Path
from typing import Any

USER_PROFILE = Path(os.environ.get("USERPROFILE") or Path.home())
ARCHIVE_ROOT = USER_PROFILE / "Documents" / "ChatGPT Archive"
REPORTS_DIR = ARCHIVE_ROOT / "reports"
INDEX_PATH = REPORTS_DIR / "asset-download-index-v2.json.xz"
OUTPUT_PATH = REPORTS_DIR / "browser-asset-cache-seed.js"
CACHE_VERSION = 1
RETRY_DELAY_MS = 30 * 24 * 60 * 60 * 1000
DEBUG = True
FILE_ID_RE = re.compile(r"^(?:file_[0-9a-fA-F]{32}|file-[A-Za-z0-9]{20,})$")


def debug(message: str) -> None:
    if DEBUG:
        print(f"DEBUG: {message}")


def classify_error(error: Any) -> str:
    text = str(error or "")
    if re.search(r"\b404\b", text):
        return "http_404"
    if re.search(r"\b403\b", text):
        return "http_403"
    if "JSON download descriptor contains no URL" in text:
        return "descriptor_no_url"
    return "other"


def main() -> int:
    debug(f"Archive root: {ARCHIVE_ROOT}")
    debug(f"Reading asset registry: {INDEX_PATH}")

    if not INDEX_PATH.is_file():
        raise FileNotFoundError(f"Asset registry not found: {INDEX_PATH}")

    index_path = INDEX_PATH
    if not index_path.is_file():
        legacy = REPORTS_DIR / "asset-download-index-v2.json"
        if legacy.is_file():
            index_path = legacy
    if index_path.name.lower().endswith(".json.xz"):
        with lzma.open(index_path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise ValueError("Invalid asset registry: results is not a list")

    now_ms = int(time.time() * 1000)
    entries: dict[str, dict[str, Any]] = {}
    skipped = 0

    for record in results:
        if not isinstance(record, dict):
            skipped += 1
            continue
        file_id = record.get("file_id")
        if not isinstance(file_id, str) or not FILE_ID_RE.fullmatch(file_id):
            skipped += 1
            continue

        status = record.get("status")
        if status == "downloaded":
            entries[file_id] = {
                "status": "downloaded",
                "filename": record.get("filename"),
                "content_type": record.get("content_type"),
                "size_bytes": record.get("size_bytes"),
                "updated_at": record.get("last_seen") or record.get("generated_at"),
                "attempts": int(record.get("attempt_count") or 1),
                "failure_class": None,
                "error": None,
                "retry_after_ms": 0,
            }
            continue

        if status == "failed":
            failure_class = record.get("failure_class") or classify_error(record.get("error"))
            entries[file_id] = {
                "status": "failed",
                "filename": None,
                "content_type": record.get("content_type"),
                "size_bytes": None,
                "updated_at": record.get("last_seen") or record.get("generated_at"),
                "attempts": int(record.get("attempt_count") or 1),
                "failure_class": failure_class,
                "error": str(record.get("error") or "Previously failed asset"),
                "retry_after_ms": (
                    now_ms + RETRY_DELAY_MS
                    if failure_class in {"http_404", "descriptor_no_url"}
                    else 0
                ),
            }
            continue

        skipped += 1

    seed_json = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    script = f'''(async () => {{
  "use strict";
  const CACHE_VERSION = {CACHE_VERSION};
  const SEED = {seed_json};

  function decodeJwtPayload(token) {{
    const parts = String(token).split(".");
    if (parts.length < 2) throw new Error("Invalid ChatGPT access token.");
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padding = "=".repeat((4 - (payload.length % 4)) % 4);
    const binary = atob(payload + padding);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    return JSON.parse(new TextDecoder("utf-8").decode(bytes));
  }}

  const response = await fetch("/api/auth/session", {{
    credentials: "include",
    headers: {{ Accept: "application/json" }},
  }});
  if (!response.ok) throw new Error(`Unable to read ChatGPT session: ${{response.status}}`);
  const session = await response.json();
  const jwt = decodeJwtPayload(session.accessToken);
  const auth = jwt["https://api.openai.com/auth"] || {{}};
  const accountId = auth.chatgpt_account_id ||
    (typeof auth.chatgpt_account_user_id === "string"
      ? auth.chatgpt_account_user_id.split("__").pop()
      : null);
  if (!accountId) throw new Error("Unable to determine ChatGPT account ID.");

  const key = `gpt-exporter.asset-cache.v1.${{accountId}}`;
  let cache = {{ version: CACHE_VERSION, entries: {{}} }};
  try {{
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed && parsed.version === CACHE_VERSION && parsed.entries) cache = parsed;
  }} catch (_) {{}}

  let added = 0;
  let upgraded = 0;
  let kept = 0;
  for (const [fileId, seedEntry] of Object.entries(SEED)) {{
    const current = cache.entries[fileId];
    if (!current) {{
      cache.entries[fileId] = seedEntry;
      added += 1;
      continue;
    }}
    if (current.status !== "downloaded" && seedEntry.status === "downloaded") {{
      cache.entries[fileId] = seedEntry;
      upgraded += 1;
      continue;
    }}
    kept += 1;
  }}

  localStorage.setItem(key, JSON.stringify(cache));
  console.log(
    `gpt-exporter asset cache seeded: ${{added}} added, ${{upgraded}} upgraded, ` +
    `${{kept}} kept; ${{Object.keys(cache.entries).length}} total.`
  );
}})().catch((error) => console.error("gpt-exporter cache seed failed:", error));
'''

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(script, encoding="utf-8")

    downloaded = sum(entry["status"] == "downloaded" for entry in entries.values())
    failed = sum(entry["status"] == "failed" for entry in entries.values())
    print(f"Seed entries : {len(entries)}")
    print(f"Downloaded   : {downloaded}")
    print(f"Failed       : {failed}")
    print(f"Skipped      : {skipped}")
    print(f"Output       : {OUTPUT_PATH}")
    print()
    print("Paste the complete generated browser-asset-cache-seed.js into the ChatGPT Firefox Console once,")
    print("then run collect_chatgpt_archive.js normally. The seed file can be deleted afterwards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
