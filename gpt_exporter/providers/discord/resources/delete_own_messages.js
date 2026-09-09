(async () => {
    "use strict";

    const EXPECTED_CHANNEL_ID = "__EXPECTED_CHANNEL_ID__";
    const EXPECTED_CURRENT_USER_ID = "__EXPECTED_CURRENT_USER_ID__";
    const CANDIDATE_IDS = __CANDIDATE_IDS_JSON__;
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const MESSAGE_SELECTOR = '[id^="chat-messages-"]';
    const targetIds = new Set(CANDIDATE_IDS.map(String));
    const deleted = new Set();
    const attempts = new Map();
    const failures = new Map();

    function currentChannelId() {
        const parts = location.pathname.split("/").filter(Boolean);
        if (parts.length < 3 || parts[0] !== "channels" || parts[1] !== "@me") {
            throw new Error("Open the target Discord DM before running this script.");
        }
        return parts[2];
    }

    function discordUserIdFromAvatarUrl(url) {
        if (!url) return null;
        const match = url.match(/(?:cdn\.discordapp\.com|media\.discordapp\.net)\/avatars\/(\d+)\//);
        return match ? match[1] : null;
    }

    function detectCurrentUser() {
        const settingsButton = document.querySelector('[aria-label="User Settings"], [aria-label="User settings"]');
        if (!settingsButton) return { id: null, detection: "not-found" };
        let container = settingsButton.parentElement;
        for (let depth = 0; container && depth < 8; depth++, container = container.parentElement) {
            const avatar = container.querySelector('img[src*="/avatars/"]');
            if (!avatar) continue;
            const avatarUrl = avatar.currentSrc || avatar.src || null;
            return { id: discordUserIdFromAvatarUrl(avatarUrl), detection: "user-settings-panel" };
        }
        return { id: null, detection: "avatar-not-found" };
    }

    function messageIdFromElement(element) {
        const match = element?.id?.match(/(\d+)$/);
        return match ? match[1] : null;
    }

    function findScroller() {
        const first = document.querySelector(MESSAGE_SELECTOR);
        if (!first) return null;
        let element = first;
        while (element) {
            const style = getComputedStyle(element);
            if ((style.overflowY === "auto" || style.overflowY === "scroll") && element.scrollHeight > element.clientHeight) {
                return element;
            }
            element = element.parentElement;
        }
        return null;
    }

    function atBottom(scroller) {
        return scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 5;
    }

    function materializedTargetRoots() {
        return [...document.querySelectorAll(MESSAGE_SELECTOR)]
            .map(root => ({ root, id: messageIdFromElement(root) }))
            .filter(item => item.id && targetIds.has(item.id) && !deleted.has(item.id));
    }

    function normalize(value) {
        return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
    }

    function isVisible(element) {
        if (!element) return false;
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    }

    function messageActionGroup(root) {
        return root.querySelector('[role="group"][aria-label="Message Actions"]');
    }

    function moreAction(root) {
        const group = messageActionGroup(root);
        if (!group) return null;
        return [...group.querySelectorAll('[role="button"]')].find(element => normalize(element.getAttribute("aria-label")) === "more") || null;
    }

    function reactMouseMoveTarget(root) {
        for (const element of [root, ...root.querySelectorAll("*")]) {
            const propsKey = Object.keys(element).find(key => key.startsWith("__reactProps$"));
            if (!propsKey) continue;
            const props = element[propsKey];
            if (typeof props?.onMouseMove === "function") return { element, props };
        }
        return null;
    }

    function materializeMessageActions(root) {
        const target = reactMouseMoveTarget(root);
        if (!target) return false;

        const rect = target.element.getBoundingClientRect();
        const clientX = rect.left + rect.width / 2;
        const clientY = rect.top + rect.height / 2;
        const event = {
            type: "mousemove",
            target: target.element,
            currentTarget: target.element,
            clientX,
            clientY,
            pageX: clientX + scrollX,
            pageY: clientY + scrollY,
            button: 0,
            buttons: 0,
            altKey: false,
            ctrlKey: false,
            metaKey: false,
            shiftKey: false,
            nativeEvent: new MouseEvent("mousemove", {
                bubbles: true,
                clientX,
                clientY,
            }),
            preventDefault() {},
            stopPropagation() {},
            persist() {},
        };

        target.props.onMouseMove(event);
        return true;
    }

    function deleteMenuItem() {
        const selectors = '[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"]';
        return [...document.querySelectorAll(selectors)].find(element => isVisible(element) && normalize(element.textContent) === "delete message") || null;
    }

    function confirmationButton() {
        const dialogs = [...document.querySelectorAll('[role="dialog"]')].filter(isVisible).reverse();
        for (const dialog of dialogs) {
            if (!normalize(dialog.textContent).includes("delete message")) continue;
            for (const button of dialog.querySelectorAll('button, [role="button"]')) {
                const text = normalize(button.textContent);
                const aria = normalize(button.getAttribute("aria-label"));
                if (text === "delete" || aria === "delete") return button;
            }
        }
        return null;
    }

    async function waitFor(predicate, timeoutMs, intervalMs = 75) {
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            const value = predicate();
            if (value) return value;
            await sleep(intervalMs);
        }
        return null;
    }

    async function deleteOne(root, id) {
        const count = (attempts.get(id) || 0) + 1;
        attempts.set(id, count);
        const targetElementId = root.id;
        try {
            root.scrollIntoView({ block: "center" });
            await sleep(120);

            if (!materializeMessageActions(root)) {
                throw new Error("React onMouseMove handler is not available inside the target message");
            }

            let more = await waitFor(() => moreAction(root), 900);
            if (!more) {
                if (!materializeMessageActions(root)) {
                    throw new Error("React onMouseMove handler is not available inside the target message");
                }
                more = await waitFor(() => moreAction(root), 900);
            }
            if (!more) throw new Error("More action is not available inside the target message");

            more.click();
            const deleteItem = await waitFor(deleteMenuItem, 1200);
            if (!deleteItem) throw new Error("Delete Message menu item was not found");

            deleteItem.click();
            const confirm = await waitFor(confirmationButton, 1500);
            if (!confirm) throw new Error("Discord delete confirmation dialog was not found");

            confirm.click();
            const removed = await waitFor(() => !document.getElementById(targetElementId), 3000);
            if (!removed) throw new Error("Target message remained in the DOM after delete confirmation");

            deleted.add(id);
            failures.delete(id);
            console.log("[9c delete] deleted", id);
            return true;
        } catch (error) {
            failures.set(id, String(error?.message || error));
            console.warn("[9c delete] could not delete", id, error);
            return false;
        }
    }

    async function processVisibleTargets() {
        let progress = false;
        for (const { root, id } of materializedTargetRoots()) {
            if ((attempts.get(id) || 0) >= 3) continue;
            if (await deleteOne(root, id)) progress = true;
            await sleep(250);
        }
        return progress;
    }

    async function sweepToBeginning(scroller) {
        let previousTop = null;
        let stable = 0;
        for (let iteration = 1; iteration <= 10000; iteration++) {
            await processVisibleTargets();
            const top = scroller.scrollTop;
            if (top <= 2 && previousTop !== null && Math.abs(top - previousTop) < 1) stable++; else stable = 0;
            if (stable >= 4) return;
            previousTop = top;
            scroller.scrollTop = 0;
            await sleep(1200);
        }
        throw new Error("Could not reach the beginning of the Discord DM.");
    }

    async function sweepToEnd(scroller) {
        let stableBottom = 0;
        let previousTop = -1;
        for (let iteration = 1; iteration <= 30000; iteration++) {
            await processVisibleTargets();
            if (deleted.size === targetIds.size) return;
            const nearBottom = atBottom(scroller);
            const top = scroller.scrollTop;
            if (nearBottom && Math.abs(top - previousTop) < 1) stableBottom++; else stableBottom = 0;
            if (stableBottom >= 5) {
                await processVisibleTargets();
                return;
            }
            previousTop = top;
            const step = Math.max(250, scroller.clientHeight * 0.78);
            scroller.scrollTop = Math.min(scroller.scrollTop + step, scroller.scrollHeight);
            await sleep(350);
        }
        throw new Error("Could not reach the end of the Discord DM.");
    }

    function downloadResult(channelId, currentUserId) {
        const unresolved = [...targetIds].filter(id => !deleted.has(id));
        const result = {
            schema_version: 1,
            exporter: "9c discord-delete",
            completed_at: new Date().toISOString(),
            channel_id: channelId,
            current_user_id: currentUserId,
            authorized_count: targetIds.size,
            deleted_count: deleted.size,
            unresolved_ids: unresolved,
            failures: Object.fromEntries([...failures.entries()].filter(([id]) => unresolved.includes(id))),
        };
        const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `discord-dm-delete-result_${channelId}_${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        console.log("[9c delete] complete", result);
        return result;
    }

    const channelId = currentChannelId();
    if (channelId !== EXPECTED_CHANNEL_ID) {
        throw new Error(`Safety stop: this payload is pinned to DM ${EXPECTED_CHANNEL_ID}, but the open DM is ${channelId}.`);
    }
    const currentUser = detectCurrentUser();
    if (!currentUser.id) throw new Error("Safety stop: could not determine the current Discord user ID.");
    if (EXPECTED_CURRENT_USER_ID && currentUser.id !== EXPECTED_CURRENT_USER_ID) {
        throw new Error(`Safety stop: current Discord user ${currentUser.id} does not match dry-run user ${EXPECTED_CURRENT_USER_ID}.`);
    }
    if (!targetIds.size) throw new Error("Safety stop: no authorized message IDs were supplied.");

    const scroller = findScroller();
    if (!scroller) throw new Error("Could not locate Discord message scroller.");

    console.log("[9c delete] authorized", { channelId, current_user_id: currentUser.id, candidates: targetIds.size });
    await sweepToBeginning(scroller);
    await sweepToEnd(scroller);
    downloadResult(channelId, currentUser.id);
})();
