import { describe, expect, it } from "vitest";
// @ts-expect-error Vitest runs in Node, while the application tsconfig is browser-only.
import { readFileSync } from "node:fs";

declare const process: { cwd: () => string };

const styles = readFileSync(`${process.cwd()}/src/styles.css`, "utf8");

describe("Stage 64F visual system", () => {
  it("defines the academic workspace tokens and fixed composer structure", () => {
    for (const token of [
      "app-background",
      "sidebar-background",
      "panel-background",
      "elevated-surface",
      "message-user-background",
      "message-assistant-background",
      "text-primary",
      "text-secondary",
      "border-subtle",
      "accent",
      "code-background",
      "citation-background",
    ])
      expect(styles).toContain(`--${token}:`);
    expect(styles).toMatch(
      /\.agent-chat-panel\s*\{[^}]*grid-template-rows:[^}]*minmax\(0,\s*1fr\) auto/s,
    );
    expect(styles).toMatch(/\.chat-compose\s*\{[^}]*justify-self:\s*center/s);
  });

  it("includes drawer behavior for medium and narrow windows", () => {
    expect(styles).toContain("@media (max-width: 1180px)");
    expect(styles).toContain("@media (max-width: 800px)");
    expect(styles).toMatch(
      /\.app-sidebar\.mobile-open\s*\{[^}]*translateX\(0\)/s,
    );
    expect(styles).toContain("prefers-reduced-motion: reduce");
  });
});
