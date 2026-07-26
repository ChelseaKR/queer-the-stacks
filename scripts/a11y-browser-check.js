#!/usr/bin/env node
"use strict";

/*
 * Browser-only accessibility contract that pa11y cannot express by itself:
 *
 * - force both light and dark prefers-color-scheme values;
 * - run the same axe runtime bundled with the pinned global pa11y install;
 * - assert that each document reflows without page-level horizontal scrolling
 *   at a 320 CSS-pixel viewport.
 *
 * Internal table scrollers remain permitted by WCAG 1.4.10's two-dimensional
 * content exception; only document-level overflow fails this gate.
 */

const { execFileSync } = require("node:child_process");
const { createRequire } = require("node:module");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const inputs = process.argv.slice(2);
if (inputs.length === 0) {
  console.error("usage: node scripts/a11y-browser-check.js FILE.html [...]");
  process.exit(2);
}

const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const globalRoot = execFileSync(npmCommand, ["root", "-g"], {
  encoding: "utf8",
}).trim();
const requireGlobal = createRequire(path.join(globalRoot, "__a11y_gate__.js"));
const puppeteer = requireGlobal("pa11y/node_modules/puppeteer");
const axePath = requireGlobal.resolve("pa11y/node_modules/axe-core/axe.min.js");

const cases = [
  { label: "desktop light", width: 1280, height: 900, mobile: false, theme: "light" },
  { label: "desktop dark", width: 1280, height: 900, mobile: false, theme: "dark" },
  { label: "320px light", width: 320, height: 800, mobile: true, theme: "light" },
  { label: "320px dark", width: 320, height: 800, mobile: true, theme: "dark" },
];

async function auditPage(browser, input, scenario) {
  const page = await browser.newPage();
  await page.setBypassCSP(true);
  await page.setViewport({
    width: scenario.width,
    height: scenario.height,
    deviceScaleFactor: 1,
    isMobile: scenario.mobile,
  });
  await page.emulateMediaFeatures([
    { name: "prefers-color-scheme", value: scenario.theme },
  ]);
  await page.goto(pathToFileURL(path.resolve(input)).href, {
    waitUntil: "networkidle0",
  });

  const darkPreference = await page.evaluate(() =>
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
  const expectedDark = scenario.theme === "dark";
  const failures = [];
  if (darkPreference !== expectedDark) {
    failures.push(
      `media emulation mismatch: expected dark=${expectedDark}, got ${darkPreference}`
    );
  }

  await page.addScriptTag({ path: axePath });
  const violations = await page.evaluate(async () => {
    const results = await window.axe.run(document);
    return results.violations.map((violation) => ({
      id: violation.id,
      help: violation.help,
      targets: violation.nodes.map((node) => node.target.join(" ")),
    }));
  });
  for (const violation of violations) {
    failures.push(
      `${violation.id}: ${violation.help} (${violation.targets.join(", ")})`
    );
  }

  if (scenario.mobile) {
    const reflow = await page.evaluate(() => {
      const root = document.documentElement;
      const body = document.body;
      return {
        clientWidth: root.clientWidth,
        scrollWidth: Math.max(root.scrollWidth, body ? body.scrollWidth : 0),
      };
    });
    if (reflow.scrollWidth > reflow.clientWidth) {
      failures.push(
        `WCAG 1.4.10 reflow: document is ${reflow.scrollWidth}px wide ` +
          `in a ${reflow.clientWidth}px viewport`
      );
    }
  }

  await page.close();
  return failures;
}

async function main() {
  const browser = await puppeteer.launch({
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
    ],
  });
  let failed = false;
  try {
    for (const input of inputs) {
      for (const scenario of cases) {
        const failures = await auditPage(browser, input, scenario);
        const label = `${path.basename(input)} · ${scenario.label}`;
        if (failures.length === 0) {
          console.log(`browser a11y: ${label}: 0 violations`);
          continue;
        }
        failed = true;
        console.error(`browser a11y: ${label}: ${failures.length} violation(s)`);
        for (const failure of failures) {
          console.error(`  - ${failure}`);
        }
      }
    }
  } finally {
    await browser.close();
  }
  if (failed) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
