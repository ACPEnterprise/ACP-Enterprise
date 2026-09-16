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
  useCandidateReview: () => ({
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
  }),
  usePriceBook: () => ({
    isPending: false,
    isError: false,
    data: {
      categories: [{ id: "category-1", name: "Drain", code: "DRAIN" }],
      tax_classifications: [{ id: "tax-1", name: "Taxable", code: "TAXABLE" }],
      service_items: [
        {
          id: "item-1",
          name: "Drain clearing",
          code: "DRAIN-CLEAR",
          status: "draft",
          customer_description: "Clear a drain.",
        },
      ],
      versions: [
        {
          id: "version-1",
          service_item_id: "item-1",
          revision: 1,
          currency: "USD",
          unit_price: "149.95",
          status: "draft",
          version: 1,
        },
      ],
      option_groups: [
        { id: "group-1", name: "Service level", code: "SERVICE-LEVEL" },
      ],
      options: [],
    },
  }),
  usePriceBookMutations: () => ({
    category: {
      isPending: false,
      isError: Boolean(mutationState.categoryError),
      error: mutationState.categoryError,
      mutateAsync: mutationState.categoryMutate,
    },
    tax: {
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
      mutateAsync: vi.fn(),
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
  }),
}));

describe("PriceBookRoute", () => {
  beforeEach(() => {
    mutationState.categoryError = null;
    mutationState.categoryMutate.mockReset();
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
    expect(screen.getByText("Drain clearing")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Create category" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Activate version" }),
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
      screen.getByRole("button", { name: "Activate version" }),
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
      screen.getByRole("button", { name: "Create option group" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Activate version" }),
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
