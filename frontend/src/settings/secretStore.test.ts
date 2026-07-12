import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  deleteProviderSecret,
  getProviderSecret,
  setProviderSecret,
} from "./secretStore";

describe("Provider secret storage", () => {
  beforeEach(() => localStorage.clear());

  it("never writes API keys to localStorage in browser development", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    await setProviderSecret("provider:test", "sk-sensitive-value");
    expect(await getProviderSecret("provider:test")).toBe("sk-sensitive-value");
    expect(spy).not.toHaveBeenCalled();
    expect(JSON.stringify(localStorage)).not.toContain("sk-sensitive-value");
    await deleteProviderSecret("provider:test");
    expect(await getProviderSecret("provider:test")).toBeNull();
  });
});
