import { FIELD_MUTATION_OFFLINE_POLICY, FIELD_PRODUCT_READINESS, fieldReadinessSummary } from "../src/field/productReadiness";

describe("field product readiness boundary", () => {
  it("classifies accepted field operations independently from source-gated domains", () => {
    expect(FIELD_PRODUCT_READINESS.ON_MY_WAY).toBe("READY_FOR_DEVICE_ACCEPTANCE");
    expect(FIELD_PRODUCT_READINESS.JOB_COMPLETION).toBe("READY_FOR_DEVICE_ACCEPTANCE");
    expect(FIELD_PRODUCT_READINESS.FIELD_PHOTOS).toBe("SOURCE_REQUIRED");
    expect(FIELD_PRODUCT_READINESS.EQUIPMENT).toBe("SOURCE_REQUIRED");
    expect(FIELD_PRODUCT_READINESS.ESTIMATE_PRESENTATION).toBe("SOURCE_REQUIRED");
    expect(FIELD_PRODUCT_READINESS.APPLE_SIGNING).toBe("EXTERNAL_GATE");
    expect(fieldReadinessSummary()).toEqual({ ready: 20, gated: 18 });
  });

  it("never classifies an offline field mutation as immediate local success", () => {
    expect(Object.values(FIELD_MUTATION_OFFLINE_POLICY)).not.toContain("OFFLINE_SUCCESS");
    expect(FIELD_MUTATION_OFFLINE_POLICY.FIELD_PHOTO).toBe("UNSUPPORTED_OFFLINE");
    expect(FIELD_MUTATION_OFFLINE_POLICY.ON_MY_WAY).toBe("SAFE_IDEMPOTENT_RETRY_AFTER_RECONCILIATION");
  });
});
