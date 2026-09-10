(() => {
    "use strict";

    function normalize(value) {
        return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
    }

    function isVisible(element) {
        if (!element) return false;
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    }

    const rows = [];
    for (const element of document.querySelectorAll("*")) {
        if (!isVisible(element)) continue;
        const text = normalize(element.textContent);
        const aria = normalize(element.getAttribute?.("aria-label"));
        const role = normalize(element.getAttribute?.("role"));
        if (text !== "delete message" && aria !== "delete message") continue;
        rows.push({
            tag: element.tagName,
            role: role || null,
            aria: aria || null,
            text: text || null,
            className: typeof element.className === "string" ? element.className : null,
            parentTag: element.parentElement?.tagName || null,
            parentRole: normalize(element.parentElement?.getAttribute?.("role")) || null,
            parentAria: normalize(element.parentElement?.getAttribute?.("aria-label")) || null,
            parentClassName: typeof element.parentElement?.className === "string" ? element.parentElement.className : null,
        });
    }

    const visibleMenus = [...document.querySelectorAll('[role="menu"], [data-list-id], [class*="menu"]')]
        .filter(isVisible)
        .map(menu => ({
            tag: menu.tagName,
            role: normalize(menu.getAttribute?.("role")) || null,
            aria: normalize(menu.getAttribute?.("aria-label")) || null,
            className: typeof menu.className === "string" ? menu.className : null,
            text: normalize(menu.textContent),
        }));

    console.log("[9c delete diagnostic] exact Delete Message matches", rows);
    console.log("[9c delete diagnostic] visible menu-like roots", visibleMenus);
    return { rows, visibleMenus };
})();
