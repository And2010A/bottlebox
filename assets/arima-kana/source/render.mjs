// Renders each SVG in the manifest to a transparent PNG with headless Chromium.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let chromium;
try {
    ({ chromium } = require("playwright"));
} catch {
    ({ chromium } = require("/opt/node-tools/node_modules/playwright"));
}

const { scale, items } = JSON.parse(readFileSync(process.argv[2], "utf8"));
const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: scale });
for (const { svg, png } of items) {
    const src = readFileSync(svg, "utf8");
    await page.setContent(`<html><body style="margin:0;background:transparent">${src}</body></html>`);
    await page.locator("svg").screenshot({ path: png, omitBackground: true });
}
await browser.close();
