import { describe, it, expect, vi, beforeEach } from "vitest";
import { getClients, sendAlert, sendAllAlerts } from "./api";

beforeEach(() => {
  global.fetch = vi.fn();
});

describe("getClients", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => [{ client_id: "CLT001" }],
    });
    const clients = await getClients();
    expect(clients).toEqual([{ client_id: "CLT001" }]);
    expect(global.fetch).toHaveBeenCalledWith("/api/clients");
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getClients()).rejects.toThrow("Failed to load clients: 500");
  });
});

describe("sendAlert", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "sent", message_id: "wamid.ABC" }),
    });
    const result = await sendAlert("CLT001");
    expect(result).toEqual({ status: "sent", message_id: "wamid.ABC" });
    expect(global.fetch).toHaveBeenCalledWith("/api/send/CLT001", { method: "POST" });
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "Alert already sent today for this client/status" }),
    });
    await expect(sendAlert("CLT001")).rejects.toThrow(
      "Alert already sent today for this client/status"
    );
  });
});

describe("sendAllAlerts", () => {
  it("returns parsed JSON array on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => [{ client_id: "CLT001", action: "sent" }],
    });
    const result = await sendAllAlerts();
    expect(result).toEqual([{ client_id: "CLT001", action: "sent" }]);
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all", { method: "POST" });
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "A bulk send is already in progress" }),
    });
    await expect(sendAllAlerts()).rejects.toThrow("A bulk send is already in progress");
  });
});
