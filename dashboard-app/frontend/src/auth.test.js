import { describe, it, expect, beforeEach } from "vitest";
import { getStoredAuthHeader, setStoredAuthHeader, clearStoredAuthHeader, buildAuthHeader } from "./auth";

beforeEach(() => {
  sessionStorage.clear();
});

describe("getStoredAuthHeader / setStoredAuthHeader", () => {
  it("returns null when nothing is stored", () => {
    expect(getStoredAuthHeader()).toBeNull();
  });

  it("returns the value set by setStoredAuthHeader", () => {
    setStoredAuthHeader("Basic abc123");
    expect(getStoredAuthHeader()).toBe("Basic abc123");
  });
});

describe("clearStoredAuthHeader", () => {
  it("removes a previously stored value", () => {
    setStoredAuthHeader("Basic abc123");
    clearStoredAuthHeader();
    expect(getStoredAuthHeader()).toBeNull();
  });
});

describe("buildAuthHeader", () => {
  it("base64-encodes username:password with a Basic prefix", () => {
    expect(buildAuthHeader("admin", "s3cret")).toBe("Basic " + btoa("admin:s3cret"));
  });
});
