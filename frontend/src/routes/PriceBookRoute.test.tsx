import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PriceBookRoute } from "./PriceBookRoute";

const authState = vi.hoisted(() => ({
  permissionCodes: [
    "COMPANY_PRICE_BOOK_READ",
    "COMPANY_PRICE_BOOK_MANAGE",
    "COMPANY_PRICE_BOOK_ACTIVATE",
  ],
}));
const mutationState = vi.hoisted(() => ({
  categoryError: null as unknown,
  categoryMutate: vi.fn(),
  categoryUpdateMutate: vi.fn(),
  versionMutate: vi.fn(),
  versionUpdateMutate: vi.fn(),
  versionLifecycleMutate: vi.fn(),
}));
const candidateReviewState = vi.hoisted(() => ({
  calls: [] as Array<Record<string, unknown>>,
}));
const catalogQueryState = vi.hoisted(() => ({
  calls: [] as Array<Record<string, unknown>>,
}));

vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: {
      id: "company-1",
      branches: [{ id: "branch-1", name: "Main", code: "MAIN" }],
    },
    permissionCodes: authState.permissionCodes,
  }),
  useHasPermission: (code: string) => authState.permissionCodes.includes(code),
}));
vi.mock("../hooks/usePriceBook", () => ({
  useCompanyTaxPolicy: () => ({
    isPending: false,
    isError: false,
    data: { current: null, history: [] },
  }),
  useActivationReadiness: () => ({
    isPending: false,
    isError: false,
    data: undefined,
  }),
  usePriceBookAudit: () => ({ isPending: false, isError: false, data: [] }),
  useCandidateReview: (params: Record<string, unknown>) => {
    candidateReviewState.calls.push(params);
    return {
      isPending: false,
      isError: false,
      data: {
        items: [
          {
            candidate_identity: "flat-rate:SVC-001",
            native_service_item_id: "item-1",
            service_code: "SVC-001",
            name: "Standard service call",
            customer_description: "Diagnostic visit",
            category: "Service Calls",
            admission_status: "admitted",
            review_flags: ["TAX_REVIEW_REQUIRED"],
            activation_blockers: ["OWNER_APPROVAL_REQUIRED"],
            candidate_prices: { standard: "129.00" },
            price_derivation: "OWNER_OVERRIDE",
            source_sheet: "Service Calls",
            source_row: 5,
            source_digest: "a".repeat(64),
            evidence_digest: "b".repeat(64),
            tax_decision_group: "CATEGORY_SERVICE_CALLS",
            conflict_reason: null,
          },
        ],
        counts: {
          admitted: 179,
          held: 39,
          material_mapping_required: 194,
          activation_ready: 0,
        },
        total: 218,
      },
    };
  },
  usePriceBook: (
    _branch: string | undefined,
    _enabled: boolean,
    filters: Record<string, unknown>,
  ) => {
    catalogQueryState.calls.push(filters);
    return {
      isPending: false,
      isError: false,
      data: {
        categories: [
          {
            id: "category-1",
            name: "Drain",
            code: "DRAIN",
            description: "Drain services",
            parent_id: null,
            position: 1,
            status: "active",
            version: 2,
          },
          {
            id: "category-2",
            name: "Sewer",
            code: "SEWER",
            description: "Sewer services",
            parent_id: "category-1",
            position: 2,
            status: "active",
            version: 1,
          },
        ],
        tax_classifications: [
          { id: "tax-1", name: "Taxable", code: "TAXABLE" },
        ],
        service_items: [
          {
            id: "item-1",
            category_id: "category-1",
            name: "Drain clearing",
            code: "DRAIN-CLEAR",
            status: "draft",
            customer_description: "Clear a drain.",
            internal_description: "Use approved cable and inspect trap.",
          },
        ],
        versions: [
          {
            id: "version-1",
            service_item_id: "item-1",
            revision: 1,
            currency: "USD",
            unit_price: "149.95",
            tax_classification_id: "tax-1",
            effective_at: "2026-10-01T08:00:00Z",
            status: "draft",
            version: 1,
            components: [
              {
                component_type: "material",
                code: null,
                label: "Expected fitting",
                quantity: "2",
                unit_cost: "4.50",
                extended_cost: "9.00",
                position: 1,
              },
            ],
          },
          {
            id: "version-active",
            service_item_id: "item-1",
            revision: 0,
            currency: "USD",
            unit_price: "139.95",
            tax_classification_id: "tax-1",
            effective_at: "2026-09-01T08:00:00Z",
            status: "active",
            version: 2,
            components: [],
          },
        ],
        option_groups: [
          {
            id: "group-1",
            name: "Service level",
            code: "SERVICE-LEVEL",
            minimum_selections: 1,
            maximum_selections: 1,
            status: "active",
          },
        ],
        options: [
          {
            id: "option-1",
            option_group_id: "group-1",
            service_item_id: "item-1",
            label: "Better",
            position: 2,
          },
        ],
        total_service_items: 75,
      },
    };
  },
  usePriceBookMutations: () => ({
    category: {
      isPending: false,
      isError: Boolean(mutationState.categoryError),
      error: mutationState.categoryError,
      mutateAsync: mutationState.categoryMutate,
    },
    categoryUpdate: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: mutationState.categoryUpdateMutate,
    },
    tax: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    companyTaxPolicy: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    updateCompanyTaxPolicy: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    certifyCompanyTaxPolicy: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    item: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    itemUpdate: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    version: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: mutationState.versionMutate,
    },
    versionUpdate: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: mutationState.versionUpdateMutate,
    },
    versionLifecycle: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: mutationState.versionLifecycleMutate,
    },
    activate: { isError: false, error: null, mutateAsync: vi.fn() },
    optionGroup: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    option: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    reviewBatch: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    reviewDecision: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    adjustmentProposal: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    adjustmentDecision: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    adjustmentMaterialize: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
    activationReview: {
      isPending: false,
      isError: false,
      error: null,
      mutateAsync: vi.fn(),
    },
  }),
}));

describe("PriceBookRoute", () => {
  beforeEach(() => {
    mutationState.categoryError = null;
    candidateReviewState.calls = [];
    catalogQueryState.calls = [];
    mutationState.categoryMutate.mockReset();
    mutationState.categoryUpdateMutate.mockReset();
    mutationState.versionMutate.mockReset();
    mutationState.versionUpdateMutate.mockReset();
    mutationState.versionLifecycleMutate.mockReset();
  });

  it("shows category hierarchy in owner browsing controls", () => {
    render(<PriceBookRoute />, { wrapper: MemoryRouter });
    expect(screen.getAllByText("Drain › Sewer").length).toBeGreaterThan(0);
  });

  it("edits category hierarchy and lifecycle through governed authority", async () => {
    mutationState.categoryUpdateMutate.mockResolvedValueOnce({});
    render(<PriceBookRoute />, { wrapper: MemoryRouter });

    fireEvent.change(screen.getByLabelText("Choose category to edit"), {
      target: { value: "category-1" },
    });
    expect(screen.getByLabelText("Category description")).toHaveValue(
      "Drain services",
    );
    fireEvent.change(screen.getByLabelText("Category status"), {
      target: { value: "archived" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save category" }));

    await waitFor(() =>
      expect(mutationState.categoryUpdateMutate).toHaveBeenCalledWith({
        categoryId: "category-1",
        data: expect.objectContaining({
          code: "DRAIN",
          status: "archived",
          expected_version: 2,
          position: 1,
        }),
      }),
    );
  });

  it("stages labor and material inputs in one draft price version", async () => {
    mutationState.versionMutate.mockResolvedValueOnce({});
    render(<PriceBookRoute />, { wrapper: MemoryRouter });

    fireEvent.change(screen.getByLabelText("Price service item"), {
      target: { value: "item-1" },
    });
    fireEvent.change(screen.getByLabelText("Tax classification"), {
      target: { value: "tax-1" },
    });
    fireEvent.change(screen.getByLabelText("Unit price"), {
      target: { value: "199" },
    });
    fireEvent.change(screen.getByLabelText("Effective time"), {
      target: { value: "2026-10-01T08:00" },
    });
    fireEvent.change(screen.getByLabelText("Component label"), {
      target: { value: "Expected labor" },
    });
    fireEvent.change(screen.getByLabelText("Expected component quantity"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Expected component unit cost"), {
      target: { value: "80" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add expected input" }));
    fireEvent.change(screen.getByLabelText("Component type"), {
      target: { value: "material" },
    });
    fireEvent.change(screen.getByLabelText("Component label"), {
      target: { value: "Expected fittings" },
    });
    fireEvent.change(screen.getByLabelText("Expected component quantity"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));

    await waitFor(() =>
      expect(mutationState.versionMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            components: [
              expect.objectContaining({
                component_type: "labor",
                label: "Expected labor",
                quantity: "2",
                unit_cost: "80",
              }),
              expect.objectContaining({
                component_type: "material",
                label: "Expected fittings",
                quantity: "3",
                unit_cost: undefined,
              }),
            ],
          }),
        }),
      ),
    );
  });

  it("edits an existing draft price without rewriting history", async () => {
    mutationState.versionUpdateMutate.mockResolvedValueOnce({});
    render(<PriceBookRoute />, { wrapper: MemoryRouter });
    fireEvent.click(screen.getByRole("button", { name: "Edit draft price" }));
    expect(screen.getByLabelText("Unit price")).toHaveValue(149.95);
    fireEvent.change(screen.getByLabelText("Unit price"), {
      target: { value: "159.95" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save draft price version" }),
    );
    await waitFor(() =>
      expect(mutationState.versionUpdateMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          versionId: "version-1",
          data: expect.objectContaining({
            expected_version: 1,
            unit_price: "159.95",
          }),
        }),
      ),
    );
  });

  it("inactivates an active price through the explicit lifecycle contract", async () => {
    mutationState.versionLifecycleMutate.mockResolvedValueOnce({});
    render(<PriceBookRoute />, { wrapper: MemoryRouter });
    fireEvent.click(
      screen.getByRole("button", { name: "Inactivate price version" }),
    );
    await waitFor(() =>
      expect(mutationState.versionLifecycleMutate).toHaveBeenCalledWith({
        versionId: "version-active",
        action: "inactivate",
        expectedVersion: 2,
      }),
    );
  });

  it("pages through the native service catalog", async () => {
    render(<PriceBookRoute />, { wrapper: MemoryRouter });

    expect(screen.getByText("Showing 1–1 of 75 services.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next services" }));

    await waitFor(() =>
      expect(catalogQueryState.calls).toContainEqual(
        expect.objectContaining({ limit: 50, offset: 50 }),
      ),
    );
  });

  it("pages through every candidate instead of hiding records past the first page", async () => {
    render(<PriceBookRoute />, { wrapper: MemoryRouter });

    expect(
      screen.getByText("Showing 1–1 of 218 candidates."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next candidates" }));

    await waitFor(() =>
      expect(candidateReviewState.calls).toContainEqual(
        expect.objectContaining({ limit: 50, offset: 50 }),
      ),
    );
  });
  it("filters coherent candidate review cohorts without activating them", async () => {
    render(<PriceBookRoute />, { wrapper: MemoryRouter });

    fireEvent.change(
      screen.getByLabelText("Filter candidate admission state"),
      {
        target: { value: "held" },
      },
    );
    fireEvent.change(
      screen.getByLabelText("Filter candidate review requirement"),
      {
        target: { value: "MATERIAL_MAPPING_REQUIRED" },
      },
    );

    await waitFor(() =>
      expect(candidateReviewState.calls).toContainEqual(
        expect.objectContaining({
          admission_status: "held",
          review_flag: "MATERIAL_MAPPING_REQUIRED",
          offset: 0,
        }),
      ),
    );
  });
  it("fails closed without Price Book read authority", () => {
    authState.permissionCodes = [];
    render(
      <MemoryRouter>
        <PriceBookRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByText("You are not authorized to view Price Book."),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Create category" }),
    ).not.toBeInTheDocument();
  });

  it("lets read-only users browse without mutation controls", () => {
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ"];
    render(
      <MemoryRouter>
        <PriceBookRoute />
      </MemoryRouter>,
    );
    expect(screen.getAllByText("Drain clearing")).not.toHaveLength(0);
    expect(
      screen.getByRole("region", { name: "Option set Service level" }),
    ).toHaveTextContent("Better · DRAIN-CLEAR · Drain clearing");
    expect(
      screen.queryByRole("button", { name: "Create category" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Review activation" }),
    ).not.toBeInTheDocument();
  });

  it("gates manage and activate controls independently", () => {
    authState.permissionCodes = [
      "COMPANY_PRICE_BOOK_READ",
      "COMPANY_PRICE_BOOK_MANAGE",
    ];
    const { unmount } = render(
      <MemoryRouter>
        <PriceBookRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("button", { name: "Create category" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Activate version" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Expected component quantity")).toBeVisible();
    expect(screen.getByLabelText("Expected component unit cost")).toBeVisible();
    expect(screen.getByText(/Expected fitting/)).toBeVisible();
    unmount();
    authState.permissionCodes = [
      "COMPANY_PRICE_BOOK_READ",
      "COMPANY_PRICE_BOOK_ACTIVATE",
    ];
    render(
      <MemoryRouter>
        <PriceBookRoute />
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("button", { name: "Create category" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Review activation" }),
    ).toBeVisible();
  });

  it("renders complete management workflows on a narrow viewport", () => {
    authState.permissionCodes = [
      "COMPANY_PRICE_BOOK_READ",
      "COMPANY_PRICE_BOOK_MANAGE",
      "COMPANY_PRICE_BOOK_ACTIVATE",
    ];
    Object.defineProperty(window, "innerWidth", {
      value: 390,
      configurable: true,
    });
    render(
      <MemoryRouter>
        <PriceBookRoute />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Price Book" })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Create service item" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Create tax classification" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Create service choice group" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Review activation" }),
    ).toBeVisible();
    expect(screen.getByText("Standard service call")).toBeVisible();
    expect(screen.getByText(/not active/i)).toBeVisible();
  });

  it("renders structured recovery without reflecting backend details", () => {
    mutationState.categoryError = {
      isAxiosError: true,
      response: {
        data: {
          detail: {
            recovery: "OWNER_ADMIN_ACTION_REQUIRED",
            message: "sql-provider-secret-canary",
          },
        },
      },
    };
    render(
      <MemoryRouter>
        <PriceBookRoute />
      </MemoryRouter>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      /administrator action/i,
    );
    expect(
      screen.queryByText(/sql-provider-secret-canary/),
    ).not.toBeInTheDocument();
  });

  it("searches draft services and opens connected owner details", () => {
    render(
      <MemoryRouter>
        <PriceBookRoute />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("Search Price Book"), {
      target: { value: "drain" },
    });
    expect(screen.getAllByText("Drain clearing")).not.toHaveLength(0);
    fireEvent.click(
      screen.getByRole("button", { name: "Open service details" }),
    );
    expect(
      screen.getByRole("region", { name: "Selected service details" }),
    ).toHaveTextContent("Drain · DRAIN-CLEAR");
    expect(
      screen.getByRole("region", { name: "Selected service details" }),
    ).toHaveTextContent("Service Calls, row 5");
    expect(
      screen.getByRole("region", { name: "Selected service details" }),
    ).toHaveTextContent("Draft — ready for review");
    expect(
      screen.getByRole("region", { name: "Selected service details" }),
    ).toHaveTextContent("Use approved cable and inspect trap.");
    fireEvent.click(screen.getByRole("button", { name: "Back to results" }));
    expect(
      screen.queryByRole("region", { name: "Selected service details" }),
    ).not.toBeInTheDocument();
  });

  it("shows an explicit empty state for unmatched searches", () => {
    render(
      <MemoryRouter>
        <PriceBookRoute />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("Search Price Book"), {
      target: { value: "not-a-real-service" },
    });
    expect(
      screen.getByText(
        "No Price Book services match this search and filter combination.",
      ),
    ).toBeVisible();
  });

  it("retains commercial evidence when a command rejects", async () => {
    mutationState.categoryMutate.mockRejectedValueOnce(
      new Error("unavailable"),
    );
    render(
      <MemoryRouter>
        <PriceBookRoute />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("Category code"), {
      target: { value: "DRAIN" },
    });
    fireEvent.change(screen.getByLabelText("Category name"), {
      target: { value: "Drain Services" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create category" }));
    await waitFor(() =>
      expect(mutationState.categoryMutate).toHaveBeenCalled(),
    );
    expect(screen.getByLabelText("Category code")).toHaveValue("DRAIN");
    expect(screen.getByLabelText("Category name")).toHaveValue(
      "Drain Services",
    );
  });
});
