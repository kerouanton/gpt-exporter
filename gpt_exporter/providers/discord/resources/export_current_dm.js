(async () => {
    "use strict";

    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const MESSAGE_SELECTOR = '[id^="chat-messages-"]';
    const DISCORD_EPOCH_MS = 1420070400000n;
    const collected = new Map();

    function currentChannelId() {
        const parts = location.pathname.split("/").filter(Boolean);
        if (parts.length < 3 || parts[0] !== "channels" || parts[1] !== "@me") {
            throw new Error("Open a Discord DM before running this script.");
        }
        return parts[2];
    }

    function messageIdFromElement(element) {
        const match = element?.id?.match(/(\d+)$/);
        return match ? match[1] : null;
    }

    function snowflakeTimestamp(id) {
        try {
            const ms = (BigInt(id) >> 22n) + DISCORD_EPOCH_MS;
            return new Date(Number(ms)).toISOString();
        } catch {
            return null;
        }
    }

    function normalizeText(value) {
        if (value == null) return null;
        const text = String(value)
            .replace(/\r\n/g, "\n")
            .replace(/\r/g, "\n")
            .replace(/\u00a0/g, " ")
            .replace(/[ \t]+\n/g, "\n")
            .replace(/\n[ \t]+/g, "\n")
            .replace(/[ \t]{2,}/g, " ")
            .trim();
        return text || null;
    }

    function unique(values) {
        return [...new Set(values.filter(Boolean))];
    }

    function uniqueObjects(values, keyFunction) {
        const seen = new Set();
        const result = [];
        for (const value of values) {
            const key = keyFunction(value);
            if (!key || seen.has(key)) continue;
            seen.add(key);
            result.push(value);
        }
        return result;
    }

    function discordUserIdFromAvatarUrl(url) {
        if (!url) return null;
        const match = url.match(/(?:cdn\.discordapp\.com|media\.discordapp\.net)\/avatars\/(\d+)\//);
        return match ? match[1] : null;
    }

    function detectCurrentUser() {
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
            const textLines = (container.innerText || "").split("\n").map(x => x.trim()).filter(Boolean);
            return {
                id,
                display_name: textLines[0] || null,
                username: textLines[1] || null,
                avatar_url: avatarUrl,
                detection: "user-settings-panel",
            };
        }
        return { id: null, display_name: null, username: null, avatar_url: null, detection: "settings-found-avatar-not-found" };
    }

    function realMessageArticle(root) {
        if (!root || root.tagName !== "LI") return null;
        return root.querySelector('[role="article"][aria-roledescription="Message"]');
    }

    function authorReferenceFromArticle(article) {
        const labelledBy = article?.getAttribute("aria-labelledby") || "";
        const token = labelledBy.split(/\s+/).find(value => /^message-username-\d+$/.test(value));
        if (!token) return null;
        return { element_id: token, message_id: token.replace(/^message-username-/, "") };
    }

    function rootForMessageId(channelId, messageId) {
        return document.getElementById(`chat-messages-${channelId}-${messageId}`);
    }

    function messageCanDelete(root) {
        return Boolean(root?.querySelector('[aria-label="Message Actions"] [aria-label="Delete"]'));
    }

    function messageCanEdit(root) {
        return Boolean(root?.querySelector('[aria-label="Message Actions"] [aria-label="Edit"]'));
    }

    function extractAuthor(article, root, currentUser, channelId) {
        const reference = authorReferenceFromArticle(article);
        if (!reference) {
            return { id: null, name: null, avatar_url: null, is_self: null, self_detection: "unresolved", source_message_id: null };
        }
        const usernameContainer = document.getElementById(reference.element_id);
        const named = usernameContainer?.querySelector("[data-text]");
        const name = normalizeText(named?.getAttribute("data-text") || named?.textContent || usernameContainer?.textContent);
        const sourceRoot = rootForMessageId(channelId, reference.message_id);
        const avatar = sourceRoot?.querySelector('img[src*="/avatars/"]');
        const avatarUrl = avatar?.currentSrc || avatar?.src || null;
        const authorId = discordUserIdFromAvatarUrl(avatarUrl);
        if (authorId && currentUser.id) {
            return { id: authorId, name, avatar_url: avatarUrl, is_self: authorId === currentUser.id, self_detection: "discord-user-id", source_message_id: reference.message_id };
        }
        if (messageCanDelete(root)) {
            return { id: authorId, name, avatar_url: avatarUrl, is_self: true, self_detection: "delete-action", source_message_id: reference.message_id };
        }
        if (messageCanEdit(root)) {
            return { id: authorId, name, avatar_url: avatarUrl, is_self: true, self_detection: "edit-action", source_message_id: reference.message_id };
        }
        return { id: authorId, name, avatar_url: avatarUrl, is_self: authorId && currentUser.id ? false : null, self_detection: authorId ? "discord-user-id" : "unresolved", source_message_id: reference.message_id };
    }

    function semanticContent(element) {
        if (!element) return null;
        const clone = element.cloneNode(true);
        for (const node of clone.querySelectorAll(['[class*="edited"]','[class*="timestamp"]','[class*="hiddenVisually"]','[aria-hidden="true"][class*="separator"]'].join(","))) node.remove();
        for (const br of clone.querySelectorAll("br")) br.replaceWith("\n");
        return normalizeText(clone.textContent);
    }

    function linkInfo(anchor) {
        const url = anchor.href || null;
        if (!url) return null;
        return { url, text: normalizeText(anchor.textContent), title: normalizeText(anchor.getAttribute("title")) };
    }

    function isDiscordAttachmentUrl(url) {
        return Boolean(url && /(?:cdn\.discordapp\.com|media\.discordapp\.net)\/attachments\//.test(url));
    }

    function attachmentIdentity(url) {
        if (!url) return null;
        try {
            const parsed = new URL(url);
            const match = parsed.pathname.match(/^\/attachments\/(\d+)\/(\d+)\/([^/]+)$/);
            if (!match) return null;
            return { channel_id: match[1], attachment_id: match[2], filename: decodeURIComponent(match[3]), key: `${match[1]}:${match[2]}`, host: parsed.hostname };
        } catch { return null; }
    }

    function mediaKind(url, tagName = null) {
        const tag = tagName?.toLowerCase();
        if (tag === "video") return "video";
        if (tag === "audio") return "audio";
        if (tag === "img") return "image";
        if (/\.(png|jpe?g|gif|webp|avif)(?:\?|$)/i.test(url || "")) return "image";
        if (/\.(mp4|webm|mov|m4v)(?:\?|$)/i.test(url || "")) return "video";
        if (/\.(mp3|wav|ogg|flac|m4a)(?:\?|$)/i.test(url || "")) return "audio";
        return "file";
    }

    function isDiscordUiAsset(url) {
        if (!url) return false;
        return url.startsWith("https://discord.com/assets/") || url.startsWith("https://cdn.discordapp.com/assets/");
    }

    function isUsefulMediaUrl(url) {
        if (!url || url.startsWith("data:") || url.startsWith("blob:") || isDiscordUiAsset(url)) return false;
        return true;
    }

    function linkedMediaFromLinks(links) {
        return uniqueObjects(links.filter(item => /\.(png|jpe?g|gif|webp|avif|mp4|webm|mov|m4v|mp3|wav|ogg|flac|m4a)(?:\?|$)/i.test(item.url || "")).map(item => ({ kind: mediaKind(item.url), url: item.url })), item => item.url);
    }

    function extractCanonicalAttachments(accessories, links) {
        const map = new Map();
        function ensure(url) {
            const identity = attachmentIdentity(url);
            if (!identity) return null;
            if (!map.has(identity.key)) map.set(identity.key, { id: identity.attachment_id, channel_id: identity.channel_id, name: identity.filename, kind: mediaKind(url), original_url: null, preview_url: null, width: null, height: null, alt: null, title: null });
            return { record: map.get(identity.key), identity };
        }
        for (const item of links) {
            if (!isDiscordAttachmentUrl(item.url)) continue;
            const found = ensure(item.url);
            if (!found) continue;
            if (found.identity.host === "cdn.discordapp.com") found.record.original_url = item.url;
            else if (!found.record.preview_url) found.record.preview_url = item.url;
        }
        if (accessories) {
            for (const element of accessories.querySelectorAll("img[src], video[src], audio[src], source[src]")) {
                const url = element.currentSrc || element.src;
                if (!isDiscordAttachmentUrl(url)) continue;
                const found = ensure(url);
                if (!found) continue;
                const record = found.record;
                if (found.identity.host === "cdn.discordapp.com") record.original_url = record.original_url || url;
                else record.preview_url = record.preview_url || url;
                record.kind = mediaKind(url, element.tagName);
                record.width = record.width || element.naturalWidth || element.videoWidth || null;
                record.height = record.height || element.naturalHeight || element.videoHeight || null;
                record.alt = record.alt || normalizeText(element.getAttribute("alt"));
                record.title = record.title || normalizeText(element.getAttribute("title"));
            }
        }
        for (const record of map.values()) {
            if (!record.original_url && record.preview_url) {
                try {
                    const preview = new URL(record.preview_url);
                    preview.hostname = "cdn.discordapp.com";
                    for (const key of ["format","quality","width","height"]) preview.searchParams.delete(key);
                    record.original_url = preview.toString();
                } catch { record.original_url = record.preview_url; }
            }
        }
        return [...map.values()];
    }

    function originalUrlFromDiscordExternalProxy(url) {
        if (!url) return null;
        try {
            const parsed = new URL(url);
            if (!/^images-ext-\d+\.discordapp\.net$/i.test(parsed.hostname)) return null;
            const httpsIndex = parsed.pathname.indexOf("/https/");
            if (httpsIndex >= 0) return `https://${parsed.pathname.slice(httpsIndex + 7)}`;
            const httpIndex = parsed.pathname.indexOf("/http/");
            if (httpIndex >= 0) return `http://${parsed.pathname.slice(httpIndex + 6)}`;
        } catch { return null; }
        return null;
    }

    function firstTextByClass(root, fragments) {
        for (const fragment of fragments) {
            const text = normalizeText(root.querySelector(`[class*="${fragment}"]`)?.textContent);
            if (text) return text;
        }
        return null;
    }

    function outermostPreviewRoots(accessories) {
        if (!accessories) return [];
        const candidates = [...accessories.querySelectorAll('[class*="embed"], [class*="preview"]')].filter(element => !element.closest('[class*="reaction"]'));
        return candidates.filter(candidate => !candidates.some(other => other !== candidate && other.contains(candidate)));
    }

    function previewPrimaryUrl(links) {
        const usable = links.filter(item => {
            if (!item?.url || isDiscordAttachmentUrl(item.url)) return false;
            try {
                const parsed = new URL(item.url);
                if (parsed.hostname.endsWith("discord.com") || parsed.hostname.endsWith("discordapp.com")) return false;
                return true;
            } catch { return false; }
        });
        const nonMedia = usable.find(item => !/\.(png|jpe?g|gif|webp|avif|mp4|webm|mov|m4v|mp3|wav|ogg|flac|m4a)(?:\?|$)/i.test(item.url));
        return nonMedia?.url || usable[0]?.url || null;
    }

    function normalizedPreviewDescription(root, siteName, title) {
        const explicit = firstTextByClass(root, ["embedDescription","description"]);
        if (explicit) return explicit;
        const lines = (normalizeText(root.innerText) || "").split("\n").map(line => line.trim()).filter(Boolean).filter(line => line !== siteName && line !== title);
        return lines.length ? lines.join("\n") : null;
    }

    function externalMediaLink(links) {
        return links.find(item => item?.url && !isDiscordAttachmentUrl(item.url) && /\.(png|jpe?g|gif|webp|avif|mp4|webm|mov|m4v)(?:\?|$)/i.test(item.url)) || null;
    }

    function extractPreviewImage(root, links) {
        const candidates = [...root.querySelectorAll("img[src], video[src]")].map(element => {
            const proxyUrl = element.currentSrc || element.src;
            if (!isUsefulMediaUrl(proxyUrl) || isDiscordAttachmentUrl(proxyUrl)) return null;
            const proxyOriginal = originalUrlFromDiscordExternalProxy(proxyUrl);
            const matchingLink = links.find(item => item?.url && (item.url === proxyOriginal || (proxyOriginal && item.url.split("?")[0] === proxyOriginal.split("?")[0])));
            return { kind: mediaKind(proxyUrl, element.tagName), original_url: matchingLink?.url || proxyOriginal || null, proxy_url: proxyUrl, alt: normalizeText(element.getAttribute("alt")), title: normalizeText(element.getAttribute("title")), width: element.naturalWidth || element.videoWidth || null, height: element.naturalHeight || element.videoHeight || null };
        }).filter(Boolean);
        if (candidates.length) {
            candidates.sort((a,b) => ((b.width||0)*(b.height||0))-((a.width||0)*(a.height||0)));
            return candidates[0];
        }
        const fallback = externalMediaLink(links);
        if (!fallback) return null;
        return { kind: mediaKind(fallback.url), original_url: fallback.url, proxy_url: null, alt: fallback.text || null, title: fallback.title || null, width: null, height: null };
    }

    function canonicalResourceUrl(url) {
        if (!url) return null;
        try {
            const parsed = new URL(url);
            parsed.pathname = parsed.pathname.replace(/%21/gi, "!");
            return parsed.href;
        } catch { return String(url).replace(/%21/gi, "!"); }
    }

    function isMediaLikeUrl(url) {
        return /\.(png|jpe?g|gif|webp|avif|mp4|webm|mov|m4v|mp3|wav|ogg|flac|m4a)(?:\?|$)/i.test(url || "");
    }

    function previewLinkScore(url) {
        try {
            const parsed = new URL(url);
            const host = parsed.hostname.toLowerCase().replace(/^www\./, "");
            const path = parsed.pathname || "/";

            if ((host === "youtube.com" || host === "m.youtube.com") && /^\/(watch|shorts)\b/i.test(path)) return 1000;
            if (host === "youtu.be" && path !== "/") return 1000;
            if (/^\/(channel|c|user)\//i.test(path)) return 10;
            if (parsed.search || parsed.hash) return 300;
            if (path && path !== "/") return 200;
            return 0;
        } catch {
            return -1;
        }
    }

    function previewSpecificLink(item) {
        const base = canonicalResourceUrl(item?.url);
        const candidates = [];
        for (const link of item?.links || []) {
            const candidate = canonicalResourceUrl(link?.url);
            if (!candidate || candidate === base || isDiscordAttachmentUrl(candidate) || isMediaLikeUrl(candidate)) continue;
            try {
                const parsed = new URL(candidate);
                if (parsed.hostname.endsWith("discord.com") || parsed.hostname.endsWith("discordapp.com")) continue;
            } catch { continue; }
            candidates.push(candidate);
        }
        candidates.sort((a,b) => previewLinkScore(b) - previewLinkScore(a));
        return candidates.find(candidate => previewLinkScore(candidate) > 10) || null;
    }

    function externalPreviewKey(item) {
        const specificLink = previewSpecificLink(item);
        if (specificLink) return specificLink;
        const imageUrl = canonicalResourceUrl(item?.image?.original_url || item?.image?.proxy_url);
        if (imageUrl) return imageUrl;
        if (item?.site_name || item?.title) return `${item.site_name || ""}|${item.title || ""}`;
        const url = canonicalResourceUrl(item?.url);
        if (url) return url;
        return item?.description || null;
    }

    function extractExternalPreviews(accessories) {
        if (!accessories) return [];
        const previews = [];
        for (const root of outermostPreviewRoots(accessories)) {
            const links = uniqueObjects([...root.querySelectorAll("a[href]")].map(linkInfo).filter(Boolean).filter(item => !isDiscordAttachmentUrl(item.url)), item => item.url);
            const siteName = firstTextByClass(root, ["embedProvider","provider"]);
            const title = firstTextByClass(root, ["embedTitle","title"]);
            const description = normalizedPreviewDescription(root, siteName, title);
            const image = extractPreviewImage(root, links);
            const url = previewPrimaryUrl(links);
            if (!url && !siteName && !title && !description && !image) continue;
            previews.push({ url, site_name: siteName, title, description, image, links });
        }
        const merged = new Map();
        for (const preview of previews) {
            const key = externalPreviewKey(preview);
            if (!key) continue;
            if (!merged.has(key)) { merged.set(key, preview); continue; }
            const target = merged.get(key);
            target.url = target.url || preview.url;
            target.site_name = target.site_name || preview.site_name;
            target.title = target.title || preview.title;
            target.description = target.description || preview.description;
            target.image = target.image || preview.image;
            target.links = uniqueObjects([...(target.links || []), ...(preview.links || [])], item => item.url);
        }
        return [...merged.values()];
    }

    function extractStickers(root) {
        const stickers = [];
        for (const element of root.querySelectorAll('[class*="sticker"] img[src], img[alt*="sticker" i]')) {
            const url = element.currentSrc || element.src;
            if (!isUsefulMediaUrl(url)) continue;
            stickers.push({ url, name: normalizeText(element.getAttribute("alt")), width: element.naturalWidth || null, height: element.naturalHeight || null });
        }
        return uniqueObjects(stickers, item => item.url);
    }

    function extractResources(root, messageId) {
        const content = root.querySelector(`#message-content-${messageId}`);
        const accessories = root.querySelector(`#message-accessories-${messageId}`);
        const contentLinks = content ? [...content.querySelectorAll("a[href]")].map(linkInfo).filter(Boolean) : [];
        const accessoryLinks = accessories ? [...accessories.querySelectorAll("a[href]")].map(linkInfo).filter(Boolean) : [];
        const links = uniqueObjects([...contentLinks, ...accessoryLinks], item => item.url);
        return { links, linked_media: linkedMediaFromLinks(links), attachments: extractCanonicalAttachments(accessories, links), external_previews: extractExternalPreviews(accessories), stickers: extractStickers(root) };
    }

    function extractMentions(contentElement) {
        if (!contentElement) return [];
        return unique([...contentElement.querySelectorAll('[class*="mention"]')].map(element => normalizeText(element.textContent)));
    }

    function extractReply(root) {
        const candidates = [...root.querySelectorAll('[class*="repliedMessage"], [class*="reply"]')];
        const reply = candidates.find(element => !element.closest('[aria-label="Message Actions"]'));
        if (!reply) return null;
        const link = reply.querySelector('a[href*="/channels/"]');
        let referencedMessageId = null;
        if (link?.href) referencedMessageId = link.href.match(/\/channels\/[^/]+\/[^/]+\/(\d+)/)?.[1] || null;
        const username = reply.querySelector('[id^="message-username-"], [data-text]');
        return { message_id: referencedMessageId, author: normalizeText(username?.getAttribute?.("data-text") || username?.textContent), text: normalizeText(reply.textContent), url: link?.href || null };
    }

    function emojiFromReactionElement(element) {
        const alt = normalizeText(element.querySelector?.("img[alt]")?.getAttribute("alt"));
        if (alt) return alt;
        const textCandidates = [...(element.querySelectorAll?.("span,div") || [])].map(node => normalizeText(node.textContent)).filter(Boolean).filter(text => !/^\d+$/.test(text));
        return textCandidates.find(text => text.length <= 16 && !/reaction|press to|reacted/i.test(text)) || null;
    }

    function parseReactionLabel(label) {
        if (!label) return { name: null, count: null, me: null };
        const countMatch = label.match(/(?:^|,\s*)(\d+)\s+reactions?\b/i);
        const nameMatch = label.match(/^\s*([^,]+?)(?:,|$)/);
        const lower = label.toLowerCase();
        return { name: normalizeText(nameMatch?.[1]), count: countMatch ? Number(countMatch[1]) : null, me: lower.includes("remove your reaction") ? true : lower.includes("press to react") ? false : null };
    }

    function reactionSemanticElements(root) {
        const result = [];
        for (const element of root.querySelectorAll('[aria-label]')) {
            if (element.closest('[aria-label="Message Actions"]')) continue;
            const label = normalizeText(element.getAttribute("aria-label"));
            if (!label || !/\breactions?\b|press to react|remove your reaction/i.test(label)) continue;
            result.push(element.matches('button,[role="button"]') ? element : element.closest('button,[role="button"]') || element);
        }
        for (const area of root.querySelectorAll('[class*="reaction"]')) {
            if (area.closest('[aria-label="Message Actions"]')) continue;
            if (area.matches('button,[role="button"]')) result.push(area);
            for (const button of area.querySelectorAll('button,[role="button"]')) result.push(button);
        }
        return uniqueObjects(result, item => item);
    }

    function extractReactions(root) {
        const logical = [];
        for (const element of reactionSemanticElements(root)) {
            const label = normalizeText(element.getAttribute("aria-label")) || normalizeText(element.querySelector?.('[aria-label]')?.getAttribute("aria-label"));
            if (!label || !/\breactions?\b|press to react|remove your reaction/i.test(label)) continue;
            const parsed = parseReactionLabel(label);
            const emoji = emojiFromReactionElement(element);
            const visibleCount = [...(element.querySelectorAll?.("span,div") || [])].map(node => normalizeText(node.textContent)).find(text => /^\d+$/.test(text || ""));
            logical.push({ emoji, name: parsed.name, count: parsed.count ?? (visibleCount ? Number(visibleCount) : null), me: parsed.me, aria_label: label });
        }
        const merged = new Map();
        for (const item of logical) {
            const key = item.name || item.emoji || item.aria_label;
            if (!key) continue;
            const existing = merged.get(key);
            if (!existing) { merged.set(key, item); continue; }
            existing.emoji = existing.emoji || item.emoji;
            existing.name = existing.name || item.name;
            existing.count = existing.count ?? item.count;
            existing.me = existing.me ?? item.me;
            existing.aria_label = existing.aria_label || item.aria_label;
        }
        return [...merged.values()];
    }

    function contentTypes(content, resources) {
        const result = [];
        if (content) result.push("text");
        if (resources.attachments.length) result.push("attachment");
        if (resources.external_previews.length) result.push("external-preview");
        if (resources.stickers.length) result.push("sticker");
        if (!result.length && resources.links.length) result.push("link");
        if (!result.length) result.push("non-text");
        return result;
    }

    function extractMessage(root, currentUser, channelId) {
        const id = messageIdFromElement(root);
        if (!id) return null;
        const article = realMessageArticle(root);
        if (!article) return null;
        const timeElement = root.querySelector(`#message-timestamp-${id}`) || root.querySelector("time[datetime]");
        if (!timeElement) return null;
        const contentElement = root.querySelector(`#message-content-${id}`);
        const author = extractAuthor(article, root, currentUser, channelId);
        const resources = extractResources(root, id);
        const content = semanticContent(contentElement);
        const types = contentTypes(content, resources);
        return { id, timestamp: timeElement.getAttribute("datetime") || snowflakeTimestamp(id), author, content, content_type: types[0], content_types: types, mentions: extractMentions(contentElement), links: resources.links, linked_media: resources.linked_media, attachments: resources.attachments, external_previews: resources.external_previews, stickers: resources.stickers, reply: extractReply(root), reactions: extractReactions(root), edited: /\(edited\)|\bedited\b/i.test(root.textContent || "") };
    }

    function mergeArrayBy(existing, incoming, keyFunction) { return uniqueObjects([...(existing || []), ...(incoming || [])], keyFunction); }

    function mergeAttachments(existing, incoming) {
        const map = new Map();
        for (const item of [...(existing || []), ...(incoming || [])]) {
            const key = item.id || item.original_url || item.preview_url;
            if (!key) continue;
            if (!map.has(key)) { map.set(key, { ...item }); continue; }
            const target = map.get(key);
            for (const field of ["channel_id","name","kind","original_url","preview_url","width","height","alt","title"]) if (target[field] == null && item[field] != null) target[field] = item[field];
        }
        return [...map.values()];
    }

    function mergeExternalPreviews(existing, incoming) {
        const map = new Map();
        for (const item of [...(existing || []), ...(incoming || [])]) {
            const key = externalPreviewKey(item);
            if (!key) continue;
            if (!map.has(key)) { map.set(key, { ...item, links: [...(item.links || [])] }); continue; }
            const target = map.get(key);
            target.url = target.url || item.url;
            target.site_name = target.site_name || item.site_name;
            target.title = target.title || item.title;
            target.description = target.description || item.description;
            target.image = target.image || item.image;
            target.links = uniqueObjects([...(target.links || []), ...(item.links || [])], link => link.url);
        }
        return [...map.values()];
    }

    function mergeReactions(existing, incoming) {
        const map = new Map();
        for (const item of [...(existing || []), ...(incoming || [])]) {
            const key = item.name || item.emoji || item.aria_label;
            if (!key) continue;
            if (!map.has(key)) { map.set(key, { ...item }); continue; }
            const target = map.get(key);
            target.emoji = target.emoji || item.emoji;
            target.name = target.name || item.name;
            target.count = Math.max(target.count || 0, item.count || 0) || null;
            if (item.me === true) target.me = true;
            else if (target.me == null && item.me === false) target.me = false;
            target.aria_label = target.aria_label || item.aria_label;
        }
        return [...map.values()];
    }

    function mergeMessage(existing, incoming) {
        if (existing.author.is_self == null && incoming.author.is_self != null) { existing.author.is_self = incoming.author.is_self; existing.author.self_detection = incoming.author.self_detection; }
        if (!existing.author.id && incoming.author.id) { existing.author.id = incoming.author.id; existing.author.avatar_url = incoming.author.avatar_url; }
        if (!existing.author.name && incoming.author.name) existing.author.name = incoming.author.name;
        if (!existing.content && incoming.content) existing.content = incoming.content;
        existing.links = mergeArrayBy(existing.links, incoming.links, item => item.url);
        existing.linked_media = mergeArrayBy(existing.linked_media, incoming.linked_media, item => item.url);
        existing.attachments = mergeAttachments(existing.attachments, incoming.attachments);
        existing.external_previews = mergeExternalPreviews(existing.external_previews, incoming.external_previews);
        existing.stickers = mergeArrayBy(existing.stickers, incoming.stickers, item => item.url);
        existing.reactions = mergeReactions(existing.reactions, incoming.reactions);
        if (!existing.reply && incoming.reply) existing.reply = incoming.reply;
        existing.edited = existing.edited || incoming.edited;
        const types = unique([...(existing.content_types || []), ...(incoming.content_types || [])]);
        existing.content_types = types;
        existing.content_type = types[0] || "non-text";
        return existing;
    }

    function fnv1a32(value) {
        let hash = 0x811c9dc5;
        for (let i = 0; i < value.length; i++) { hash ^= value.charCodeAt(i); hash = Math.imul(hash, 0x01000193); }
        return (hash >>> 0).toString(16).padStart(8, "0");
    }

    function stableResourceId(prefix, key) { return `${prefix}:${fnv1a32(String(key))}`; }
    function addMessageId(record, messageId) { if (!record.message_ids.includes(messageId)) record.message_ids.push(messageId); }

    function buildGlobalResources(messages) {
        const attachmentMap = new Map(), externalMediaMap = new Map(), stickerMap = new Map(), previewMap = new Map();
        function ensureExternalMedia(item, messageId, source) {
            const originalUrl = canonicalResourceUrl(item?.original_url || item?.url || null);
            const proxyUrl = canonicalResourceUrl(item?.proxy_url || null);
            const key = originalUrl || proxyUrl;
            if (!key || isDiscordAttachmentUrl(originalUrl) || isDiscordAttachmentUrl(proxyUrl)) return null;
            let record = externalMediaMap.get(key);
            if (!record) {
                record = { resource_id: stableResourceId("external-media", key), kind: item?.kind || mediaKind(key), original_url: originalUrl, proxy_url: proxyUrl, alt: item?.alt || null, title: item?.title || null, width: item?.width || null, height: item?.height || null, sources: [], message_ids: [] };
                externalMediaMap.set(key, record);
            }
            record.kind = record.kind || item?.kind || mediaKind(key);
            record.original_url = record.original_url || originalUrl;
            record.proxy_url = record.proxy_url || proxyUrl;
            record.alt = record.alt || item?.alt || null;
            record.title = record.title || item?.title || null;
            record.width = record.width || item?.width || null;
            record.height = record.height || item?.height || null;
            if (source && !record.sources.includes(source)) record.sources.push(source);
            addMessageId(record, messageId);
            return record.resource_id;
        }
        for (const message of messages) {
            const refs = [];
            for (const attachment of message.attachments || []) {
                const key = attachment.id || attachment.original_url || attachment.preview_url;
                if (!key) continue;
                const resourceId = attachment.id ? `attachment:${attachment.id}` : stableResourceId("attachment", key);
                let record = attachmentMap.get(key);
                if (!record) {
                    record = { resource_id: resourceId, attachment_id: attachment.id || null, channel_id: attachment.channel_id || null, name: attachment.name || null, kind: attachment.kind || null, original_url: canonicalResourceUrl(attachment.original_url), preview_url: canonicalResourceUrl(attachment.preview_url), width: attachment.width || null, height: attachment.height || null, alt: attachment.alt || null, title: attachment.title || null, message_ids: [] };
                    attachmentMap.set(key, record);
                }
                addMessageId(record, message.id); refs.push(record.resource_id);
            }
            for (const linked of message.linked_media || []) {
                const resourceId = ensureExternalMedia(linked, message.id, "linked-media");
                if (resourceId) refs.push(resourceId);
            }
            for (const preview of message.external_previews || []) {
                const previewKey = externalPreviewKey(preview);
                if (!previewKey) continue;
                const canonicalKey = canonicalResourceUrl(previewKey) || previewKey;
                const previewId = stableResourceId("external-preview", canonicalKey);
                let imageResourceId = null;
                if (preview.image) { imageResourceId = ensureExternalMedia(preview.image, message.id, "external-preview-image"); if (imageResourceId) refs.push(imageResourceId); }
                let record = previewMap.get(canonicalKey);
                if (!record) {
                    record = { resource_id: previewId, url: canonicalResourceUrl(preview.url), site_name: preview.site_name || null, title: preview.title || null, description: preview.description || null, image_resource_id: imageResourceId, links: [...(preview.links || [])], message_ids: [] };
                    previewMap.set(canonicalKey, record);
                } else {
                    record.url = record.url || canonicalResourceUrl(preview.url);
                    record.site_name = record.site_name || preview.site_name || null;
                    record.title = record.title || preview.title || null;
                    record.description = record.description || preview.description || null;
                    record.image_resource_id = record.image_resource_id || imageResourceId;
                    record.links = uniqueObjects([...(record.links || []), ...(preview.links || [])], item => item.url);
                }
                addMessageId(record, message.id); refs.push(record.resource_id);
            }
            for (const sticker of message.stickers || []) {
                const url = canonicalResourceUrl(sticker.url);
                if (!url) continue;
                let record = stickerMap.get(url);
                if (!record) { record = { resource_id: stableResourceId("sticker", url), url, name: sticker.name || null, width: sticker.width || null, height: sticker.height || null, message_ids: [] }; stickerMap.set(url, record); }
                addMessageId(record, message.id); refs.push(record.resource_id);
            }
            message.resource_refs = unique(refs);
        }
        const attachments = [...attachmentMap.values()], externalMedia = [...externalMediaMap.values()], stickers = [...stickerMap.values()], externalPreviews = [...previewMap.values()];
        return { attachments, external_media: externalMedia, stickers, external_previews: externalPreviews, counts: { attachments: attachments.length, external_media: externalMedia.length, stickers: stickers.length, external_previews: externalPreviews.length, downloadable_assets: attachments.length + externalMedia.length + stickers.length, total: attachments.length + externalMedia.length + stickers.length + externalPreviews.length } };
    }

    function collectMaterializedMessages(currentUser, channelId) {
        const roots = [...document.querySelectorAll(MESSAGE_SELECTOR)];
        let real = 0, added = 0, merged = 0;
        for (const root of roots) {
            const message = extractMessage(root, currentUser, channelId);
            if (!message) continue;
            real++;
            const existing = collected.get(message.id);
            if (!existing) { collected.set(message.id, message); added++; }
            else { mergeMessage(existing, message); merged++; }
        }
        return { materialized_elements: roots.length, real_messages: real, added, merged, total: collected.size };
    }

    function findScroller() {
        const first = document.querySelector(MESSAGE_SELECTOR);
        if (!first) return null;
        let element = first;
        while (element) {
            const style = getComputedStyle(element);
            if ((style.overflowY === "auto" || style.overflowY === "scroll") && element.scrollHeight > element.clientHeight) return element;
            element = element.parentElement;
        }
        return null;
    }

    function realMessageIds() {
        const ids = [];
        for (const root of document.querySelectorAll(MESSAGE_SELECTOR)) {
            if (!realMessageArticle(root)) continue;
            const id = messageIdFromElement(root);
            if (id) ids.push(id);
        }
        return ids;
    }
    function oldestMaterializedRealId() { return realMessageIds()[0] || null; }
    function newestMaterializedRealId() { const ids = realMessageIds(); return ids.length ? ids[ids.length - 1] : null; }
    function atBottom(scroller) { return scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 5; }

    async function traverseToBeginning(scroller, currentUser, channelId) {
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
    }

    async function traverseToEnd(scroller, currentUser, channelId) {
        let previousNewest = null, stableBottom = 0, previousTotal = collected.size;
        for (let iteration = 1; iteration <= 30000; iteration++) {
            const beforeTop = scroller.scrollTop, beforeHeight = scroller.scrollHeight;
            const step = Math.max(250, scroller.clientHeight * 0.78);
            scroller.scrollTop = Math.min(scroller.scrollTop + step, scroller.scrollHeight);
            await sleep(350);
            const status = collectMaterializedMessages(currentUser, channelId);
            const newest = newestMaterializedRealId();
            const nearBottom = atBottom(scroller);
            const noNewMessages = collected.size === previousTotal;
            const newestStable = newest && newest === previousNewest;
            const noMovement = Math.abs(scroller.scrollTop - beforeTop) < 1;
            console.log("[9c exporter v15] ENRICH", { iteration, newest, nearBottom, noNewMessages, ...status });
            if (nearBottom && newestStable && noNewMessages) stableBottom++; else stableBottom = 0;
            if (stableBottom >= 5) { collectMaterializedMessages(currentUser, channelId); return; }
            if (noMovement && !nearBottom) {
                scroller.scrollTop = Math.min(beforeTop + scroller.clientHeight, Math.max(beforeHeight, scroller.scrollHeight));
                await sleep(350);
                collectMaterializedMessages(currentUser, channelId);
            }
            previousNewest = newest;
            previousTotal = collected.size;
        }
        throw new Error("Could not reach end of Discord DM during enrichment sweep.");
    }

    function downloadJson(payload, filename) {
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url; anchor.download = filename; anchor.style.display = "none";
        document.body.appendChild(anchor); anchor.click(); anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    const channelId = currentChannelId();
    const currentUser = detectCurrentUser();
    console.log("[9c exporter v15] Current user", currentUser);
    if (!currentUser.id) throw new Error("Could not determine the current Discord user ID.");
    const scroller = findScroller();
    if (!scroller) throw new Error("Could not locate Discord message scroller.");
    collectMaterializedMessages(currentUser, channelId);
    const launchNewestMessageId = newestMaterializedRealId();
    const launchAtBottom = atBottom(scroller);
    console.log("[9c exporter v15] Launch state", { newest_visible_message: launchNewestMessageId, at_bottom: launchAtBottom, initially_collected: collected.size });
    console.log("[9c exporter v15] Phase 1: finding beginning");
    await traverseToBeginning(scroller, currentUser, channelId);
    const launchNewestWasCollected = Boolean(launchNewestMessageId && collected.has(launchNewestMessageId));
    const downwardTraversalUsed = true;
    const enrichmentSweepUsed = true;
    console.log("[9c exporter v15] Phase 2: enrichment sweep toward end");
    await traverseToEnd(scroller, currentUser, channelId);

    const messages = [...collected.values()].sort((a,b) => BigInt(a.id) < BigInt(b.id) ? -1 : BigInt(a.id) > BigInt(b.id) ? 1 : 0);
    const selfMessages = messages.filter(message => message.author.is_self === true);
    const otherMessages = messages.filter(message => message.author.is_self === false);
    const unresolvedMessages = messages.filter(message => message.author.is_self == null);
    const participantMap = new Map();
    for (const message of messages) {
        const author = message.author;
        const key = author.id || `${author.name}|${author.is_self}`;
        if (!key || participantMap.has(key)) continue;
        participantMap.set(key, { id: author.id, name: author.name, avatar_url: author.avatar_url, is_self: author.is_self });
    }
    const resources = buildGlobalResources(messages);
    const nonTextMessages = messages.filter(message => !message.content).map(message => ({ id: message.id, timestamp: message.timestamp, author: message.author.name, is_self: message.author.is_self, content_type: message.content_type, content_types: message.content_types, link_count: message.links.length, attachment_count: message.attachments.length, external_preview_count: message.external_previews.length, sticker_count: message.stickers.length, resource_ref_count: message.resource_refs.length }));
    const attachmentRecords = messages.flatMap(message => message.attachments);
    const reactionRecords = messages.flatMap(message => message.reactions);
    const externalPreviewRecords = messages.flatMap(message => message.external_previews);
    const diagnostics = {
        launch_newest_message_id: launchNewestMessageId,
        launch_at_bottom: launchAtBottom,
        launch_newest_was_collected: launchNewestWasCollected,
        downward_traversal_used: downwardTraversalUsed,
        enrichment_sweep_used: enrichmentSweepUsed,
        first_message_id: messages[0]?.id || null,
        first_timestamp: messages[0]?.timestamp || null,
        last_message_id: messages.at(-1)?.id || null,
        last_timestamp: messages.at(-1)?.timestamp || null,
        messages_with_content: messages.filter(m => m.content).length,
        messages_without_content: messages.filter(m => !m.content).length,
        messages_with_links: messages.filter(m => m.links.length).length,
        messages_with_linked_media: messages.filter(m => m.linked_media.length).length,
        messages_with_attachments: messages.filter(m => m.attachments.length).length,
        attachment_records: attachmentRecords.length,
        attachment_records_with_preview: attachmentRecords.filter(a => a.preview_url).length,
        messages_with_external_previews: messages.filter(m => m.external_previews.length).length,
        external_preview_records: externalPreviewRecords.length,
        external_preview_records_with_image: externalPreviewRecords.filter(p => p.image).length,
        external_preview_records_with_original_image: externalPreviewRecords.filter(p => p.image?.original_url).length,
        messages_with_stickers: messages.filter(m => m.stickers.length).length,
        messages_with_replies: messages.filter(m => m.reply).length,
        messages_with_reactions: messages.filter(m => m.reactions.length).length,
        reaction_records: reactionRecords.length,
        edited_messages: messages.filter(m => m.edited).length,
        messages_with_resource_refs: messages.filter(m => m.resource_refs.length).length,
        global_resource_counts: resources.counts,
        non_text_messages: nonTextMessages,
    };

    const payload = {
        schema_version: 15,
        exporter: "9c discord-exporter",
        exported_at: new Date().toISOString(),
        source_url: location.href,
        current_user: currentUser,
        conversation: { channel_id: channelId, title: document.title, type: "dm", participants: [...participantMap.values()] },
        message_count: messages.length,
        self_message_count: selfMessages.length,
        other_message_count: otherMessages.length,
        unresolved_author_count: unresolvedMessages.length,
        diagnostics,
        resources,
        messages,
    };

    window.__discord9cExport = payload;
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const filename = `discord-dm-export-v15_${channelId}_${timestamp}.json`;
    downloadJson(payload, filename);
    console.log(`[9c exporter v15] Complete: ${messages.length} messages`);
    console.log(`[9c exporter v15] Self: ${selfMessages.length}`);
    console.log(`[9c exporter v15] Other: ${otherMessages.length}`);
    console.log(`[9c exporter v15] Unresolved: ${unresolvedMessages.length}`);
    console.log(`[9c exporter v15] Range: ${diagnostics.first_timestamp} → ${diagnostics.last_timestamp}`);
    console.log(`[9c exporter v15] Attachment records: ${diagnostics.attachment_records}`);
    console.log(`[9c exporter v15] Reactions: ${diagnostics.messages_with_reactions} messages / ${diagnostics.reaction_records} logical reactions`);
    console.log(`[9c exporter v15] External previews: ${diagnostics.messages_with_external_previews} messages / ${diagnostics.external_preview_records} logical previews`);
    console.log(`[9c exporter v15] External previews with image: ${diagnostics.external_preview_records_with_image}`);
    console.log(`[9c exporter v15] External previews with original image: ${diagnostics.external_preview_records_with_original_image}`);
    console.log("[9c exporter v15] Global resources", resources.counts);
    console.log(`[9c exporter v15] Enrichment sweep used: ${enrichmentSweepUsed}`);
    console.log(`[9c exporter v15] Downloaded: ${filename}`);
    return payload;
})();
