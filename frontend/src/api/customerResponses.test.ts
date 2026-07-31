import { describe, expect, it } from "vitest";

import { normalizeCustomerDetail, normalizeCustomerList } from "./customerResponses";

const migrated = { id: "customer-1", display_name: "Migrated customer", customer_type: "residential", status: "active", marketing_source: null, preferred_contact_method: "phone", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };

describe("customer response normalization", () => {
  it("preserves a missing migrated source as null", () => {
    expect(normalizeCustomerList({ items: [migrated], total: 1, limit: 20, offset: 0 }).items[0].source).toBeNull();
  });

  it("normalizes canonical detail collections without inventing optional values", () => {
    const detail = normalizeCustomerDetail({ ...migrated, contacts: [], locations: [{ id: "location-1", customer_id: "customer-1", address: "Synthetic street", city: "Town", state: "NY", postal_code: "00000", created_at: "", updated_at: "" }] });
    expect(detail.source).toBeNull();
    expect(detail.properties).toHaveLength(1);
    expect(detail.properties[0].property_type).toBeNull();
  });
});
