import { afterEach, describe, expect, it, vi } from "vitest";

import { normalizeCustomerSource } from "../types/customers";
import { apiClient } from "./client";
import { getCustomer, listCustomers, updateCustomer } from "./customers";

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

  it("adapts the current Preview customer-detail contract without legacy arrays", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        id: "customer-preview-1",
        company_id: "company-1",
        customer_number: "CUS-000001",
        customer_type: "residential",
        display_name: "Preview Customer",
        legal_name: null,
        preferred_contact_method: "phone",
        marketing_source: null,
        tax_exempt: false,
        notes: "Migrated customer context",
        status: "active",
        primary_contact_id: "contact-1",
        created_at: "2026-08-01T12:00:00Z",
        updated_at: "2026-08-01T12:00:00Z",
        preferred_contact: {
          id: "contact-1",
          customer_id: "customer-preview-1",
          first_name: "Preview",
          last_name: "Customer",
          title: null,
          email: null,
          mobile_phone: "555-0100",
          office_phone: null,
          is_preferred: true,
          active: true,
          notes: null,
          created_at: "2026-08-01T12:00:00Z",
          updated_at: "2026-08-01T12:00:00Z",
        },
        contacts: [],
        locations: [
          {
            id: "location-1",
            customer_id: "customer-preview-1",
            nickname: null,
            address: "10 Preview Street",
            address_line_2: null,
            city: "Albany",
            state: "NY",
            postal_code: "12207",
            country: "US",
            gate_code: null,
            property_notes: null,
            active: true,
            created_at: "2026-08-01T12:00:00Z",
            updated_at: "2026-08-01T12:00:00Z",
          },
        ],
        active_service_locations: [],
        inactive_service_locations: [],
        metadata: {
          company_id: "company-1",
          customer_number: "CUS-000001",
          status: "active",
          customer_type: "residential",
          preferred_contact_method: "phone",
          created_at: "2026-08-01T12:00:00Z",
          updated_at: "2026-08-01T12:00:00Z",
        },
      },
    } as never);

    const response = await getCustomer("customer-preview-1");

    expect(response).toMatchObject({
      business_name: "Preview Customer",
      primary_phone: "555-0100",
      source: "unknown",
      internal_notes: "Migrated customer context",
      contacts: [],
      notes: [],
    });
    expect(response.properties).toEqual([
      expect.objectContaining({
        id: "location-1",
        address_line_1: "10 Preview Street",
        property_type: "unknown",
        sewer_septic: "unknown",
      }),
    ]);
  });

  it("limits customer edits to the current authoritative update contract", async () => {
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({
      data: { ...customerResponse, properties: [], contacts: [], notes: [] },
    } as never);

    await updateCustomer("customer-1", {
      customer_type: "residential",
      first_name: null,
      last_name: null,
      business_name: "Preview Customer",
      primary_phone: "555-0100",
      email: "preview@example.com",
      preferred_contact_method: "phone",
      status: "active",
      source: "legacy_import",
      internal_notes: "Not part of the bounded update contract",
    });

    expect(patch).toHaveBeenCalledWith("/api/v1/customers/customer-1", {
      customer_type: "residential",
      display_name: "Preview Customer",
      preferred_contact_method: "phone",
      status: "active",
    });
  });
});
