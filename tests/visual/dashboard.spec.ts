import { test, expect } from "@playwright/test";
import path from "path";

const VIEWPORTS = [
  { name: "2048x1152", width: 2048, height: 1152 },
  { name: "1920x1080", width: 1920, height: 1080 },
  { name: "1707x960", width: 1707, height: 960 },
] as const;

const SCREENSHOT_DIR = path.join(process.cwd(), "docs", "visual-regression");

for (const viewport of VIEWPORTS) {
  test(`dashboard reference screenshot @ ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });

    await page.goto("/", { waitUntil: "networkidle" });

    // Wait for client-only performance chart to render
    await page.waitForSelector(".chart-panel", { state: "visible" });
    await page.waitForTimeout(800);

    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    }));

    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.innerWidth);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, `dashboard-${viewport.name}.png`),
      fullPage: true,
      animations: "disabled",
    });
  });
}
