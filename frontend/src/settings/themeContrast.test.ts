import { describe, expect, it } from "vitest";
// @ts-expect-error Vitest runs in Node, while the application tsconfig is browser-only.
import { readFileSync } from "node:fs";

declare const process: { cwd: () => string };

const stylesheet = readFileSync(`${process.cwd()}/src/styles.css`, "utf8");

type ThemeTokens = Record<string, string>;

function tokensFor(selector: string): ThemeTokens {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const block = stylesheet.match(new RegExp(`${escaped}\\s*\\{([^}]+)\\}`));
  if (!block) throw new Error(`Missing theme block: ${selector}`);
  return Object.fromEntries(
    [...block[1].matchAll(/--([\w-]+):\s*(#[\da-f]{6})\s*;/gi)].map(
      ([, name, value]) => [name, value],
    ),
  );
}

function relativeLuminance(hex: string): number {
  const channels = [1, 3, 5].map(
    (start) => Number.parseInt(hex.slice(start, start + 2), 16) / 255,
  );
  const [red, green, blue] = channels.map((value) =>
    value <= 0.04045 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4),
  );
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrast(foreground: string, background: string): number {
  const light = Math.max(
    relativeLuminance(foreground),
    relativeLuminance(background),
  );
  const dark = Math.min(
    relativeLuminance(foreground),
    relativeLuminance(background),
  );
  return (light + 0.05) / (dark + 0.05);
}

describe("theme contrast tokens", () => {
  it.each([
    [":root", "light"],
    ['[data-theme="dark"]', "dark"],
  ])("keeps key %s surfaces at WCAG AA contrast", (selector) => {
    const tokens = tokensFor(selector);
    const pairs = [
      ["text-primary", "background"],
      ["text-primary", "assistant-message-background"],
      ["text-primary", "input-background"],
      ["text-primary", "surface-secondary"],
      ["user-message-text", "user-message-background"],
      ["link", "assistant-message-background"],
      ["link", "citation-highlight-background"],
    ];
    for (const [foreground, background] of pairs) {
      expect(
        contrast(tokens[foreground], tokens[background]),
        `${foreground} on ${background}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("uses semantic tokens for chat, Markdown, KaTeX, Sources, and the composer", () => {
    expect(stylesheet).toMatch(
      /\.assistant-message\s*\{[^}]*var\(--assistant-message-background\)/s,
    );
    expect(stylesheet).toMatch(
      /\.user-message\s*\{[^}]*var\(--user-message-background\)/s,
    );
    expect(stylesheet).toMatch(
      /\.chat-compose\s*\{[^}]*var\(--assistant-message-background\)/s,
    );
    expect(stylesheet).toMatch(
      /\.source-card\s*\{[^}]*var\(--source-border\)[^}]*var\(--surface-secondary\)/s,
    );
    expect(stylesheet).toMatch(
      /\.markdown-message pre\s*\{[^}]*var\(--code-background\)/s,
    );
    expect(stylesheet).toMatch(/\.markdown-message \.katex/);
  });

  it("keeps component color literals inside theme token declarations only", () => {
    const componentRules = stylesheet
      .replace(/:root\s*\{[^}]+\}/s, "")
      .replace(/\[data-theme="dark"\]\s*\{[^}]+\}/s, "");
    expect(componentRules).not.toMatch(/#[\da-f]{3,8}|rgba?\(/i);
  });
});
