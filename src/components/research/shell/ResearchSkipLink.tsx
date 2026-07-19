"use client";

import type { MouseEvent } from "react";

/**
 * Skip link that moves keyboard focus to #research-main (#303 P2).
 * Native hash navigation alone is not enough for a reliable Playwright/a11y path
 * unless the target is programmatically focused after activation.
 */
export function ResearchSkipLink() {
  function focusMain(event: MouseEvent<HTMLAnchorElement>) {
    const main = document.getElementById("research-main");
    if (!(main instanceof HTMLElement)) return;
    // Keep hash navigation; ensure the landmark receives focus.
    event.preventDefault();
    main.focus();
    main.scrollIntoView({ block: "start" });
    if (window.location.hash !== "#research-main") {
      window.history.replaceState(null, "", "#research-main");
    }
  }

  return (
    <a
      href="#research-main"
      className="rs-skip-link"
      data-testid="research-skip-link"
      onClick={focusMain}
    >
      Zum Research-Inhalt springen
    </a>
  );
}
