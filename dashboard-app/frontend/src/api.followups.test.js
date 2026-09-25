import { describe, it, expect, vi, beforeEach } from "vitest";
import { getFollowupCount, sendFollowups, getSendFollowupsStatus } from "./api";

beforeEach(() => {
  global.fetch = vi.fn();
});

describe("follow-up api", () => {
  it("getFollowupCount returns the eligible count info", async () => {
    const info = { eligible: 3, separate_key: true, remaining_quota: 297 };
    global.fetch.mockResolvedValue({ ok: true, json: async () => info });
    expect(await getFollowupCount()).toEqual(info);
    expect(global.fetch).toHaveBeenCalledWith("/api/followup-count", { credentials: "include", headers: {} });
  });

  it("getFollowupCount throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getFollowupCount()).rejects.toThrow("Failed to load follow-up count: 500");
  });

  it("sendFollowups POSTs and returns the job id", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "j1" }) });
    expect(await sendFollowups()).toEqual({ job_id: "j1" });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-followups", {
      method: "POST", credentials: "include", headers: {},
    });
  });

  it("sendFollowups surfaces the server's error detail", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 409, json: async () => ({ detail: "A bulk email send is already in progress" }),
    });
    await expect(sendFollowups()).rejects.toThrow("A bulk email send is already in progress");
  });

  it("getSendFollowupsStatus fetches the job status", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ sent: 1, done: true }) });
    expect(await getSendFollowupsStatus("j1")).toEqual({ sent: 1, done: true });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-followups/status/j1", { credentials: "include", headers: {} });
  });
});
