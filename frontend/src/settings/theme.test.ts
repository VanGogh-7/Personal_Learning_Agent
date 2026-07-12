import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { applyTheme, readThemePreference, useThemePreference } from "./theme";

describe("theme settings", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    window.matchMedia = vi.fn(
      () =>
        ({
          matches: false,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }) as unknown as MediaQueryList,
    );
  });

  it("defaults to system and persists the user selection", () => {
    expect(readThemePreference()).toBe("system");
    const { result } = renderHook(() => useThemePreference());
    act(() => result.current[1]("dark"));
    expect(localStorage.getItem("pla-theme")).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("resolves system appearance", () => {
    vi.mocked(window.matchMedia).mockReturnValue({
      matches: true,
    } as MediaQueryList);
    applyTheme("system");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
