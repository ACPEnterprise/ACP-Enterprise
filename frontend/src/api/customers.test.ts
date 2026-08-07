import { afterEach, describe, expect, it, vi } from "vitest";

import { normalizeCustomerSource } from "../types/customers";
import { apiClient } from "./client";
import { getCustomer, listCustomers } from "./customers";

const customerResponse = {
  id: "customer-1",
  customer_type: "individual",
  first_name: "Alex",
  last_name: "Rivera",
  business_name: null,
  primary_phone: "555-0100",
  secondary_phone: null,
  email: null,
  preferred_contact_method: "phone",
  status: "active",
  source: null,
  is_vip: false,
  internal_notes: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  archived_at: null,
};

afterEach(() => vi.restoreAllMocks());

describe("customer response normalization", () => {
  it.each([
    [null, "unknown"],
    [undefined, "unknown"],
    ["", "unknown"],
    ["   ", "unknown"],
    [" Legacy Import ", "legacy_import"],
    ["HOME-ADVISOR", "home_advisor"],
    [{ legacy: true }, "unknown"],
  ])("normalizes source %j to %s", (source, expected) => {
    expect(normalizeCustomerSource(source)).toBe(expected);
  });

  it("normalizes nullable sources in customer-list responses", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { items: [customerResponse], total: 1, limit: 20, offset: 0 },
    } as never);

    const response = await listCustomers("", 20, 0);

    expect(response.items[0]?.source).toBe("unknown");
  });

  it("normalizes missing sources in customer-detail responses", async () => {
    const detail: Record<string, unknown> = { ...customerResponse };
    delete detail.source;
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { ...detail, properties: [], contacts: [], notes: [] },
    } as never);

    const response = await getCustomer("customer-1");

    expect(response.source).toBe("unknown");
  });
});
