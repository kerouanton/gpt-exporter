"""Browser-collector integration for the Discord provider.

The provider deliberately does not read Discord tokens, cookies, passwords or local
browser profiles. Collection runs in the user's already-authenticated Discord web
session, mirroring the established ChatGPT collector workflow.
"""

from __future__ import annotations

import json
import time
import webbrowser
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

EXPORT_GLOB = "discord-dm-export-v15_*.json"
EXPORTER_NAME = "9c discord-exporter"
SCHEMA_VERSION = 15

# Discord renders both Unicode and custom emoji as inline <img alt="…"> in
# message content. The historical v15 resource used textContent and therefore
# dropped those emoji. Apply a backwards-compatible source overlay when the
# collector is copied to the browser; existing v15 exports remain valid.
_SEMANTIC_CONTENT_SENTINEL = (
    '        for (const br of clone.querySelectorAll("br")) br.replaceWith("\\n");\n'
    '        return normalizeText(clone.textContent);'
)
_SEMANTIC_CONTENT_EMOJI_PATCH = (
    '        for (const image of clone.querySelectorAll("img[alt]")) {\n'
    '            const alt = normalizeText(image.getAttribute("alt"));\n'
    '            if (alt) image.replaceWith(alt);\n'
    '        }\n'
    '        for (const br of clone.querySelectorAll("br")) br.replaceWith("\\n");\n'
    '        return normalizeText(clone.textContent);'
)

# Discord localizes the account/settings controls, so the old exact English
# aria-label lookup fails on e.g. French clients. Prefer the known account panel
# when available, then use a strict language-independent geometric fallback: a
# unique Discord avatar in the bottom-left account strip, outside message rows.
_CURRENT_USER_SENTINEL = '''    function detectCurrentUser() {
        const settingsButton = document.querySelector('[aria-label="User Settings"], [aria-label="User settings"]');
        if (!settingsButton) {
            return { id: null, display_name: null, username: null, avatar_url: null, detection: "not-found" };
        }
        let container = settingsButton.parentElement;
        for (let depth = 0; container && depth < 8; depth++, container = container.parentElement) {
            const avatar = container.querySelector('img[src*="/avatars/"]');
            if (!avatar) continue;
            const avatarUrl = avatar.currentSrc || avatar.src || null;
            const id = discordUserIdFromAvatarUrl(avatarUrl);
            const textLines = (container.innerText || "").split("\\n").map(x => x.trim()).filter(Boolean);
            return {
                id,
                display_name: textLines[0] || null,
                username: textLines[1] || null,
                avatar_url: avatarUrl,
                detection: "user-settings-panel",
            };
        }
        return { id: null, display_name: null, username: null, avatar_url: null, detection: "settings-found-avatar-not-found" };
    }'''

_CURRENT_USER_PATCH = '''    function currentUserFromAvatar(avatar, detection) {
        if (!avatar) return null;
        const avatarUrl = avatar.currentSrc || avatar.src || null;
        const id = discordUserIdFromAvatarUrl(avatarUrl);
        if (!id) return null;
        let container = avatar.parentElement;
        let textLines = [];
        for (let depth = 0; container && depth < 6; depth++, container = container.parentElement) {
            const lines = (container.innerText || "").split("\\n").map(x => x.trim()).filter(Boolean);
            if (lines.length && lines.length <= 8) { textLines = lines; break; }
        }
        return {
            id,
            display_name: textLines[0] || normalizeText(avatar.getAttribute("alt")) || null,
            username: null,
            avatar_url: avatarUrl,
            detection,
        };
    }

    function detectCurrentUser() {
        const settingsButton = document.querySelector([
            '[aria-label="User Settings"]',
            '[aria-label="User settings"]',
            '[aria-label="Paramètres utilisateur"]',
            '[aria-label="Paramètres de l’utilisateur"]',
            '[aria-label="Benutzereinstellungen"]'
        ].join(','));
        if (settingsButton) {
            let container = settingsButton.parentElement;
            for (let depth = 0; container && depth < 8; depth++, container = container.parentElement) {
                const avatar = container.querySelector('img[src*="/avatars/"]');
                const found = currentUserFromAvatar(avatar, "user-settings-panel");
                if (found) return found;
            }
        }

        const candidates = [...document.querySelectorAll('img[src*="/avatars/"]')]
            .filter(avatar => !avatar.closest('[id^="chat-messages-"]'))
            .filter(avatar => {
                const rect = avatar.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 && rect.left >= 0 && rect.left < 64 &&
                    rect.top >= 0 && rect.bottom >= window.innerHeight - 140 && rect.bottom <= window.innerHeight;
            });
        const byId = new Map();
        for (const avatar of candidates) {
            const avatarUrl = avatar.currentSrc || avatar.src || null;
            const id = discordUserIdFromAvatarUrl(avatarUrl);
            if (id && !byId.has(id)) byId.set(id, avatar);
        }
        if (byId.size === 1) {
            return currentUserFromAvatar([...byId.values()][0], "bottom-left-account-avatar");
        }
        return {
            id: null,
            display_name: null,
            username: null,
            avatar_url: null,
            detection: byId.size ? "ambiguous-bottom-left-account-avatars" : "not-found",
        };
    }'''

# Short DMs can fit entirely in Discord's message pane. In that case the pane
# still has overflow-y: scroll/auto, but scrollHeight == clientHeight. The base
# collector used scrollability as an existence test and rejected these valid DMs.
_SCROLLER_SENTINEL = '''    function findScroller() {
        const first = document.querySelector(MESSAGE_SELECTOR);
        if (!first) return null;
        let element = first;
        while (element) {
            const style = getComputedStyle(element);
            if ((style.overflowY === "auto" || style.overflowY === "scroll") && element.scrollHeight > element.clientHeight) return element;
            element = element.parentElement;
        }
        return null;
    }'''

_SCROLLER_PATCH = '''    function findScroller() {
        const first = document.querySelector(MESSAGE_SELECTOR);
        if (!first) return null;
        let element = first;
        let nonScrollableFallback = null;
        while (element) {
            const style = getComputedStyle(element);
            if (style.overflowY === "auto" || style.overflowY === "scroll") {
                if (!nonScrollableFallback) nonScrollableFallback = element;
                if (element.scrollHeight > element.clientHeight) return element;
            }
            element = element.parentElement;
        }
        return nonScrollableFallback;
    }'''

# Discord's message list is virtualized. In a large DM, scrollTop can briefly be
# zero while Discord has only loaded a recent window; the old collector treated
# four stable iterations at scrollTop == 0 as proof that the beginning had been
# reached. Keep v15 compatibility but overlay a much more conservative traversal
# that explicitly records whether a real top-of-history marker was observed.
_TOP_TRAVERSAL_SENTINEL = '''    async function traverseToBeginning(scroller, currentUser, channelId) {
        let previousOldest = null, stable = 0;
        for (let iteration = 1; iteration <= 10000; iteration++) {
            const status = collectMaterializedMessages(currentUser, channelId);
            const oldest = oldestMaterializedRealId();
            console.log("[9c exporter v15] UP", { iteration, oldest, ...status });
            if (oldest && oldest === previousOldest) stable++; else stable = 0;
            previousOldest = oldest;
            if (stable >= 4 && scroller.scrollTop <= 2) { collectMaterializedMessages(currentUser, channelId); return; }
            scroller.scrollTop = 0;
            await sleep(1600);
        }
        throw new Error("Could not reach beginning of Discord DM.");
    }'''

_TOP_TRAVERSAL_PATCH = '''    function topOfHistoryMarkerVisible(scroller) {
        const text = normalizeText(scroller?.innerText) || "";
        if (/this is the beginning of (?:your )?(?:direct message|dm|conversation|chat) history/i.test(text)) return true;
        if (/c['’]est le début de (?:votre|l['’])?(?:historique|conversation)/i.test(text)) return true;
        if (/dies ist der anfang (?:deines|eures|der) (?:direktnachrichten|unterhaltung)/i.test(text)) return true;
        return Boolean(scroller?.querySelector('[class*="emptyChannelIcon"], [class*="welcomeMessage"], [class*="channelIntro"]'));
    }

    async function traverseToBeginning(scroller, currentUser, channelId) {
        let previousOldest = null, stable = 0, topMarkerStable = 0;
        for (let iteration = 1; iteration <= 10000; iteration++) {
            const status = collectMaterializedMessages(currentUser, channelId);
            const oldest = oldestMaterializedRealId();
            const topMarker = topOfHistoryMarkerVisible(scroller);
            console.log("[9c exporter v15] UP", { iteration, oldest, topMarker, stable, ...status });
            if (oldest && oldest === previousOldest) stable++; else stable = 0;
            if (topMarker && scroller.scrollTop <= 2) topMarkerStable++; else topMarkerStable = 0;
            previousOldest = oldest;
            if (topMarkerStable >= 2) {
                collectMaterializedMessages(currentUser, channelId);
                return { reached_top: true, top_marker_detected: true, stable_iterations: stable, oldest_message_id: oldest };
            }
            // Do not hang forever when Discord stops loading older history. A
            // stable scrollTop==0 without an explicit beginning marker is a
            // partial/unverified capture, never deletion evidence.
            if (stable >= 20 && scroller.scrollTop <= 2) {
                collectMaterializedMessages(currentUser, channelId);
                return { reached_top: false, top_marker_detected: false, stable_iterations: stable, oldest_message_id: oldest };
            }
            scroller.scrollTop = 0;
            await sleep(1600);
        }
        return { reached_top: false, top_marker_detected: false, stable_iterations: stable, oldest_message_id: previousOldest };
    }'''

_BEGINNING_CALL_SENTINEL = '''    console.log("[9c exporter v15] Phase 1: finding beginning");
    await traverseToBeginning(scroller, currentUser, channelId);
    const launchNewestWasCollected = Boolean(launchNewestMessageId && collected.has(launchNewestMessageId));'''

_BEGINNING_CALL_PATCH = '''    console.log("[9c exporter v15] Phase 1: finding beginning");
    const beginning = await traverseToBeginning(scroller, currentUser, channelId);
    console.log("[9c exporter v15] Beginning evidence", beginning);
    const launchNewestWasCollected = Boolean(launchNewestMessageId && collected.has(launchNewestMessageId));'''

_DIAGNOSTICS_SENTINEL = '''        launch_newest_was_collected: launchNewestWasCollected,
        downward_traversal_used: downwardTraversalUsed,
        enrichment_sweep_used: enrichmentSweepUsed,'''

_DIAGNOSTICS_PATCH = '''        launch_newest_was_collected: launchNewestWasCollected,
        downward_traversal_used: downwardTraversalUsed,
        enrichment_sweep_used: enrichmentSweepUsed,
        reached_top_of_conversation: beginning.reached_top === true,
        top_of_history_marker_detected: beginning.top_marker_detected === true,
        top_stable_iterations: beginning.stable_iterations || 0,
        history_complete: Boolean(beginning.reached_top === true && launchAtBottom && launchNewestWasCollected && atBottom(scroller)),'''

_COMPLETION_LOG_SENTINEL = '''    console.log(`[9c exporter v15] Enrichment sweep used: ${enrichmentSweepUsed}`);
    console.log(`[9c exporter v15] Downloaded: ${filename}`);'''

_COMPLETION_LOG_PATCH = '''    console.log(`[9c exporter v15] Enrichment sweep used: ${enrichmentSweepUsed}`);
    console.log(`[9c exporter v15] History complete: ${diagnostics.history_complete}`);
    console.log(`[9c exporter v15] Reached top: ${diagnostics.reached_top_of_conversation}`);
    console.log(`[9c exporter v15] Downloaded: ${filename}`);'''


@dataclass(frozen=True, slots=True)
class CollectorExport:
    path: Path
    channel_id: str
    title: str
    message_count: int
    exported_at: str | None


def collector_javascript() -> str:
    resource = files("gpt_exporter.providers.discord.resources").joinpath(
        "export_current_dm.js"
    )
    source = resource.read_text(encoding="utf-8")
    replacements = (
        (_SEMANTIC_CONTENT_SENTINEL, _SEMANTIC_CONTENT_EMOJI_PATCH, "semanticContent"),
        (_CURRENT_USER_SENTINEL, _CURRENT_USER_PATCH, "current-user detection"),
        (_SCROLLER_SENTINEL, _SCROLLER_PATCH, "short-DM scroller detection"),
        (_TOP_TRAVERSAL_SENTINEL, _TOP_TRAVERSAL_PATCH, "top traversal"),
        (_BEGINNING_CALL_SENTINEL, _BEGINNING_CALL_PATCH, "beginning call"),
        (_DIAGNOSTICS_SENTINEL, _DIAGNOSTICS_PATCH, "history diagnostics"),
        (_COMPLETION_LOG_SENTINEL, _COMPLETION_LOG_PATCH, "completion logging"),
    )
    for sentinel, patch, label in replacements:
        if sentinel not in source:
            raise RuntimeError(f"Packaged Discord collector {label} changed unexpectedly")
        source = source.replace(sentinel, patch, 1)
    return source


def open_discord(channel_id: str | None = None) -> bool:
    channel_id = str(channel_id or "").strip()
    if channel_id and not channel_id.isdigit():
        raise ValueError(f"Invalid Discord channel ID: {channel_id!r}")
    url = "https://discord.com/channels/@me"
    if channel_id:
        url = f"{url}/{channel_id}"
    return bool(webbrowser.open(url, new=2))


def snapshot_exports(download_directory: Path) -> set[Path]:
    directory = Path(download_directory).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Download directory does not exist: {directory}")
    return {path.resolve() for path in directory.glob(EXPORT_GLOB)}


def validate_collector_export(path: Path) -> CollectorExport:
    path = Path(path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Discord collector export root must be a JSON object")
    if payload.get("exporter") != EXPORTER_NAME:
        raise ValueError("JSON file was not produced by the 9c Discord collector")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported Discord collector schema: {payload.get('schema_version')!r}"
        )

    conversation = payload.get("conversation")
    messages = payload.get("messages")
    if not isinstance(conversation, dict):
        raise ValueError("Discord collector export has no conversation object")
    if not isinstance(messages, list):
        raise ValueError("Discord collector export has no messages array")

    channel_id = str(conversation.get("channel_id") or "").strip()
    if not channel_id.isdigit():
        raise ValueError("Discord collector export has an invalid channel ID")
    if payload.get("message_count") != len(messages):
        raise ValueError(
            "Discord collector message count mismatch: "
            f"declared={payload.get('message_count')!r}, actual={len(messages)}"
        )

    ids: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Discord collector contains a non-object message")
        message_id = str(message.get("id") or "")
        if not message_id.isdigit():
            raise ValueError("Discord collector contains an invalid message ID")
        ids.append(message_id)
    if len(ids) != len(set(ids)):
        raise ValueError("Discord collector contains duplicate message IDs")

    return CollectorExport(
        path=path,
        channel_id=channel_id,
        title=str(conversation.get("title") or f"Discord DM {channel_id}"),
        message_count=len(messages),
        exported_at=(
            str(payload["exported_at"])
            if isinstance(payload.get("exported_at"), str)
            else None
        ),
    )


def wait_for_new_export(
    download_directory: Path,
    *,
    known_files: set[Path] | None = None,
    timeout_seconds: float = 7200.0,
    poll_seconds: float = 0.5,
) -> CollectorExport:
    directory = Path(download_directory).expanduser().resolve()
    known = {path.resolve() for path in (known_files or set())}
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        candidates = sorted(
            (
                path
                for path in directory.glob(EXPORT_GLOB)
                if path.resolve() not in known
            ),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for candidate in candidates:
            try:
                return validate_collector_export(candidate).path
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                last_error = error
        time.sleep(poll_seconds)

    detail = f" Last validation error: {last_error}" if last_error else ""
    raise TimeoutError(f"Timed out waiting for Discord export in {directory}.{detail}")
