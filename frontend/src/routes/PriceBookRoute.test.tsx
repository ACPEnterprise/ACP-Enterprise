import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PriceBookRoute } from "./PriceBookRoute";

const authState = vi.hoisted(() => ({
  permissionCodes: ["COMPANY_PRICE_BOOK_READ", "COMPANY_PRICE_BOOK_MANAGE", "COMPANY_PRICE_BOOK_ACTIVATE"],
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
  usePriceBookReview: () => ({ data: { rows: [] }, isLoading: false, isError: false }),
  usePriceBook: () => ({
    isPending: false,
    isError: false,
    data: {
      categories: [{ id: "category-1", name: "Drain", code: "DRAIN" }],
      tax_classifications: [{ id: "tax-1", name: "Taxable", code: "TAXABLE" }],
      service_items: [{ id: "item-1", category_id: "category-1", name: "Drain clearing", code: "DRAIN-CLEAR", status: "draft", customer_description: "Clear a drain.", current_version_id: null }],
      versions: [{ id: "version-1", service_item_id: "item-1", tax_classification_id: "tax-1", revision: 1, currency: "USD", unit_price: "149.95", effective_at: "2026-09-15T12:00:00Z", expires_at: null, status: "draft", version: 1, components: [] }],
      option_groups: [{ id: "group-1", name: "Service level", code: "SERVICE-LEVEL" }],
      options: [],
    },
  }),
  usePriceBookMutations: () => ({
    category: { isPending: false, isError: Boolean(mutationState.categoryError), error: mutationState.categoryError, mutateAsync: mutationState.categoryMutate }, updateCategory: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, tax: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, updateTax: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, item: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, updateItem: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, version: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, updateVersion: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, activate: { isError: false, error: null, mutateAsync: vi.fn() }, transition: { isError: false, error: null, mutateAsync: vi.fn() }, optionGroup: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, option: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, validateBulk: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, createBulk: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, bulkReview: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() }, reviewDecision: { isPending: false, isError: false, error: null, mutateAsync: vi.fn() },
  }),
}));

describe("PriceBookRoute", () => {
  beforeEach(() => {
    mutationState.categoryError = null;
    mutationState.categoryMutate.mockReset();
  });
  it("fails closed without Price Book read authority", () => {
    authState.permissionCodes = [];
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.getByText("You are not authorized to view Price Book.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Create category" })).not.toBeInTheDocument();
  });

  it("lets read-only users browse without mutation controls", () => {
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ"];
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.getAllByText("Drain clearing")[0]).toBeVisible();
    expect(screen.queryByRole("button", { name: "Create category" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review and activate" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Internal unit cost")).not.toBeInTheDocument();
  });

  it("gates manage and activate controls independently", () => {
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ", "COMPANY_PRICE_BOOK_MANAGE"];
    const { unmount } = render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Create category" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Review and activate" })).not.toBeInTheDocument();
    unmount();
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ", "COMPANY_PRICE_BOOK_ACTIVATE"];
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.queryByRole("button", { name: "Create category" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review and activate" })).toBeVisible();
  });

  it("renders complete management workflows on a narrow viewport", () => {
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ", "COMPANY_PRICE_BOOK_MANAGE", "COMPANY_PRICE_BOOK_ACTIVATE"];
    Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Price Book" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Create service item" })).toBeVisible();
    expect(screen.getByLabelText("Internal unit cost")).toBeVisible();
    expect(screen.getByRole("heading", { name: "All County draft builder" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Review and activate" })).toBeVisible();
  });

  it("filters the operator catalog without exposing internal identifiers", () => {
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ"];
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Search Price Book"), { target: { value: "missing" } });
    expect(screen.getByText("No services match these filters.")).toBeVisible();
    expect(screen.queryByText("item-1")).not.toBeInTheDocument();
  });

  it("renders structured recovery without reflecting backend details", () => {
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ", "COMPANY_PRICE_BOOK_MANAGE"];
    mutationState.categoryError = {
      isAxiosError: true,
      response: { data: { detail: { recovery: "OWNER_ADMIN_ACTION_REQUIRED", message: "sql-provider-secret-canary" } } },
    };
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.getByRole("alert")).toHaveTextContent(/administrator action/i);
    expect(screen.queryByText(/sql-provider-secret-canary/)).not.toBeInTheDocument();
  });

  it("retains commercial evidence when a command rejects", async () => {
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ", "COMPANY_PRICE_BOOK_MANAGE"];
    mutationState.categoryMutate.mockRejectedValueOnce(new Error("unavailable"));
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Category code"), {
      target: { value: "DRAIN" },
    });
    fireEvent.change(screen.getByLabelText("Category name"), {
      target: { value: "Drain Services" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create category" }));
    await waitFor(() => expect(mutationState.categoryMutate).toHaveBeenCalled());
    expect(screen.getByLabelText("Category code")).toHaveValue("DRAIN");
    expect(screen.getByLabelText("Category name")).toHaveValue("Drain Services");
  });
});
