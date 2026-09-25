import { describe, it, expect, vi, beforeEach } from "vitest";
import { importRenewals } from "./api";

beforeEach(() => {
  global.fetch = vi.fn();
});

describe("importRenewals", () => {
  const file = new File(["x"], "BIS.xlsx");

  it("POSTs the file with apply=false for a preview", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ renewed: 1 }) });
    expect(await importRenewals(file, false)).toEqual({ renewed: 1 });
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("/api/import-renewals");
    expect(options.method).toBe("POST");
    expect(options.body.get("file")).toBe(file);
    expect(options.body.get("apply")).toBe("false");
  });

  it("sends apply=true when applying", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    await importRenewals(file, true);
    expect(global.fetch.mock.calls[0][1].body.get("apply")).toBe("true");
  });

  it("throws the server's error detail", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 400, json: async () => ({ detail: "bad columns" }) });
    await expect(importRenewals(file, false)).rejects.toThrow("bad columns");
  });

  it("falls back to a status message when the error has no detail", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500, json: async () => { throw new Error("no body"); } });
    await expect(importRenewals(file, false)).rejects.toThrow("Import failed: 500");
  });
});
