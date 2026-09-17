import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as estimatesApi from "../api/estimates";
import * as priceBookApi from "../api/priceBook";
import { EstimatesRoute } from "./EstimatesRoute";

let permissions = new Set<string>();
vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: {
      default_branch_id: "11111111-1111-4111-8111-111111111111",
      branches: [
        {
          id: "11111111-1111-4111-8111-111111111111",
          name: "Main",
          code: "MAIN",
        },
      ],
    },
  }),
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../hooks/useCustomers", () => ({
  useCustomerSearch: () => ({
    isLoading: false,
    isError: false,
    data: {
      items: [{ id: "customer-1", display_name: "Michael Customer" }],
      page: 1,
      page_size: 25,
      total_count: 1,
      total_pages: 1,
    },
  }),
  useCustomerDetail: (customerId: string | null) => ({
    isLoading: false,
    data: customerId
      ? {
          id: customerId,
          display_name: "Michael Customer",
          properties: [
            {
              id: "location-1",
              address_line_1: "10 Main Street",
              city: "Clearwater",
            },
          ],
        }
      : undefined,
  }),
}));
vi.mock("../api/estimates", () => ({
  listEstimates: vi.fn().mockResolvedValue({
    total: 1,
    items: [
      {
        id: "estimate-1",
        branch_id: "branch-1",
        customer_id: "customer-1",
        service_location_id: null,
        estimate_number: "EST-000001",
        status: "draft",
        acceptance_status: "not_requested",
        version: 1,
        proposal_title: "Heating proposal",
        currency: "USD",
        total_amount: "97.20",
        expires_at: null,
        updated_at: "2026-08-30T12:00:00Z",
      },
    ],
  }),
  getEstimate: vi.fn().mockResolvedValue({
    id: "estimate-1",
    branch_id: "branch-1",
    customer_id: "customer-1",
    service_location_id: "location-1",
    estimate_number: "EST-000001",
    status: "draft",
    acceptance_status: "not_requested",
    version: 1,
    current_revision: {
      id: "revision-1",
      revision_number: 1,
      proposal_title: "Heating proposal",
      currency: "USD",
      subtotal_amount: "100.00",
      discount_type: "fixed",
      discount_value: "10.00",
      discount_amount: "10.00",
      taxable_basis: "90.00",
      tax_amount: "7.20",
      total_amount: "97.20",
      customer_message: null,
      terms: null,
      lines: [
        {
          id: "line-1",
          title: "Heating service",
          description: null,
          snapshot_id: "snapshot-1",
          snapshot_digest: "a".repeat(64),
          quantity: "1",
          unit_price: "100",
          line_total: "100",
          currency: "USD",
          option_group_id: "group-1",
          option_id: "option-1",
          discount_allocation: "10",
          discounted_basis: "90",
          tax_amount: "7.20",
          taxable: true,
        },
      ],
    },
  }),
  createEstimate: vi.fn(),
  reviseEstimate: vi.fn(),
  transitionEstimate: vi.fn(),
  decideEstimate: vi.fn(),
  convertEstimateToJob: vi.fn(),
}));
vi.mock("../api/priceBook", () => ({
  getPriceBook: vi.fn().mockResolvedValue({
    categories: [
      { id: "category-1", code: "DRAIN", name: "Drain Cleaning", status: "active" },
    ],
    tax_classifications: [],
    option_groups: [
      { id: "group-1", code: "CHOICE", name: "Good / Better / Best", status: "active" },
    ],
    options: [
      {
        id: "option-1",
        option_group_id: "group-1",
        service_item_id: "service-1",
        label: "Better",
        position: 2,
      },
    ],
    service_items: [
      {
        id: "service-1",
        code: "HEAT-1",
        name: "Heating service",
        customer_description: "Heating service",
        status: "active",
        current_version_id: "version-1",
      },
    ],
    versions: [],
    total_service_items: 1,
    limit: 500,
    offset: 0,
    costs_visible: false,
  }),
  createCommercialSnapshot: vi.fn().mockResolvedValue({ id: "snapshot-1" }),
  createCategory: vi.fn(),
  createTax: vi.fn(),
  createServiceItem: vi.fn(),
  updateServiceItem: vi.fn(),
  createPriceVersion: vi.fn(),
  activatePriceVersion: vi.fn(),
  createOptionGroup: vi.fn(),
  addOption: vi.fn(),
  createReviewBatch: vi.fn(),
  decideReviewBatch: vi.fn(),
  createAdjustmentProposal: vi.fn(),
  decideAdjustmentProposal: vi.fn(),
  materializeAdjustmentProposal: vi.fn(),
}));

function renderRoute(path = "/estimates") {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <EstimatesRoute />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EstimatesRoute", () => {
  beforeEach(() => {
    permissions = new Set();
    vi.mocked(estimatesApi.createEstimate).mockReset();
    vi.mocked(estimatesApi.listEstimates).mockClear();
    vi.mocked(estimatesApi.getEstimate).mockClear();
    vi.mocked(priceBookApi.getPriceBook).mockClear();
    vi.mocked(priceBookApi.createCommercialSnapshot).mockClear();
  });
  it("fails closed without read permission", () => {
    renderRoute();
    expect(
      screen.getByText("You are not authorized to view Estimates."),
    ).toBeVisible();
    expect(estimatesApi.listEstimates).not.toHaveBeenCalled();
    expect(estimatesApi.getEstimate).not.toHaveBeenCalled();
  });
  it("keeps management controls separate from read access", async () => {
    permissions = new Set(["COMPANY_ESTIMATE_READ"]);
    renderRoute("/estimates?id=estimate-1");
    expect((await screen.findAllByText("Heating proposal"))[0]).toBeVisible();
    expect(screen.queryByText("Create proposal")).not.toBeInTheDocument();
    expect(screen.getByText("Selected customer option")).toBeVisible();
    expect(screen.getByText("1 × $100.00 each")).toBeVisible();
    expect(screen.getByText("Estimate pipeline")).toBeVisible();
    expect(screen.getByText("EST-000001")).toBeVisible();
    expect(estimatesApi.listEstimates).toHaveBeenCalledWith(
      undefined,
      undefined,
      25,
      0,
    );
  });
  it("pages the Estimate pipeline without hiding older records", async () => {
    permissions = new Set(["COMPANY_ESTIMATE_READ"]);
    vi.mocked(estimatesApi.listEstimates).mockResolvedValueOnce({
      total: 30,
      items: [
        {
          id: "estimate-1",
          branch_id: "branch-1",
          customer_id: "customer-1",
          service_location_id: null,
          estimate_number: "EST-000001",
          status: "draft",
          acceptance_status: "not_requested",
          version: 1,
          proposal_title: "Heating proposal",
          currency: "USD",
          total_amount: "97.20",
          expires_at: null,
          updated_at: "2026-08-30T12:00:00Z",
        },
      ],
    });
    renderRoute();
    expect(await screen.findByText("Showing 1–1 of 30 Estimates.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next Estimates" }));
    await waitFor(() =>
      expect(estimatesApi.listEstimates).toHaveBeenCalledWith(
        undefined,
        undefined,
        25,
        25,
      ),
    );
  });
  it("renders mobile-safe management controls with totals", async () => {
    permissions = new Set([
      "COMPANY_ESTIMATE_READ",
      "COMPANY_ESTIMATE_MANAGE",
      "COMPANY_PRICE_BOOK_READ",
      "COMPANY_CUSTOMER_READ",
    ]);
    renderRoute("/estimates?id=estimate-1");
    expect(await screen.findByText("Create proposal")).toBeVisible();
    expect((await screen.findAllByText("Heating proposal"))[0]).toBeVisible();
    expect(screen.getAllByText("$97.20")).toHaveLength(2);
    expect(screen.getByLabelText("Discount type")).toBeVisible();
  });
  it("searches and filters the active Price Book during Estimate authoring", async () => {
    permissions = new Set([
      "COMPANY_ESTIMATE_READ",
      "COMPANY_ESTIMATE_MANAGE",
      "COMPANY_PRICE_BOOK_READ",
      "COMPANY_CUSTOMER_READ",
    ]);
    renderRoute();
    expect(screen.getByLabelText("Branch")).toHaveValue(
      "11111111-1111-4111-8111-111111111111",
    );
    fireEvent.change(screen.getByLabelText("Estimate Customer"), {
      target: { value: "customer-1" },
    });
    fireEvent.change(await screen.findByLabelText("Estimate Service Location"), {
      target: { value: "location-1" },
    });
    expect(
      await screen.findByRole("option", { name: "10 Main Street, Clearwater" }),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Estimate Service Location"), {
      target: { value: "location-1" },
    });
    expect(screen.getByLabelText("Estimate Service Location")).toHaveValue(
      "location-1",
    );
    await screen.findByRole("option", { name: "HEAT-1 · Heating service" });

    fireEvent.change(screen.getByLabelText("Search active Price Book services"), {
      target: { value: "drain" },
    });
    await waitFor(() =>
      expect(priceBookApi.getPriceBook).toHaveBeenCalledWith(
        "11111111-1111-4111-8111-111111111111",
        expect.objectContaining({ search: "drain", itemStatus: "active" }),
      ),
    );

    fireEvent.change(screen.getByLabelText("Filter active Price Book category"), {
      target: { value: "category-1" },
    });
    await waitFor(() =>
      expect(priceBookApi.getPriceBook).toHaveBeenCalledWith(
        "11111111-1111-4111-8111-111111111111",
        expect.objectContaining({
          search: "drain",
          categoryId: "category-1",
          itemStatus: "active",
        }),
      ),
    );
  });
  it("retains proposal evidence and hides backend details after rejection", async () => {
    permissions = new Set([
      "COMPANY_ESTIMATE_READ",
      "COMPANY_ESTIMATE_MANAGE",
      "COMPANY_PRICE_BOOK_READ",
      "COMPANY_CUSTOMER_READ",
    ]);
    vi.mocked(estimatesApi.createEstimate).mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        data: {
          detail: {
            recovery: "USER_CORRECTION_REQUIRED",
            message: "sql-provider-secret-canary",
          },
        },
      },
    });
    renderRoute();
    await screen.findByText("Create proposal");
    fireEvent.change(screen.getByLabelText("Estimate Customer"), {
      target: { value: "customer-1" },
    });
    await screen.findByRole("option", { name: "HEAT-1 · Heating service" });
    fireEvent.change(await screen.findByLabelText("Price Book service"), {
      target: { value: "service-1" },
    });
    fireEvent.change(screen.getByLabelText("Proposal title"), {
      target: { value: "Heating proposal" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create immutable Estimate" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        /requires correction/i,
      ),
    );
    expect(screen.getByLabelText("Proposal title")).toHaveValue(
      "Heating proposal",
    );
    expect(
      screen.queryByText(/sql-provider-secret-canary/),
    ).not.toBeInTheDocument();
  });
  it("keeps the customer-facing option label when staging an Estimate line", async () => {
    permissions = new Set([
      "COMPANY_ESTIMATE_READ",
      "COMPANY_ESTIMATE_MANAGE",
      "COMPANY_PRICE_BOOK_READ",
      "COMPANY_CUSTOMER_READ",
    ]);
    renderRoute();
    await screen.findByRole("option", { name: "Good / Better / Best" });
    fireEvent.change(screen.getByLabelText("Customer option set"), {
      target: { value: "group-1" },
    });
    fireEvent.change(await screen.findByLabelText("Price Book option"), {
      target: { value: "option-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add another service" }));
    expect(screen.getByText(/Better · Heating service/)).toBeVisible();
  });

  it("preserves staged services while searching for another line", async () => {
    permissions = new Set([
      "COMPANY_ESTIMATE_READ",
      "COMPANY_ESTIMATE_MANAGE",
      "COMPANY_PRICE_BOOK_READ",
      "COMPANY_CUSTOMER_READ",
    ]);
    vi.mocked(estimatesApi.createEstimate).mockResolvedValue({ id: "estimate-2" } as never);
    renderRoute();
    fireEvent.change(screen.getByLabelText("Estimate Customer"), {
      target: { value: "customer-1" },
    });
    const serviceSelect = await screen.findByLabelText("Price Book service");
    await screen.findByRole("option", { name: "HEAT-1 · Heating service" });
    fireEvent.change(serviceSelect, {
      target: { value: "service-1" },
    });
    expect(serviceSelect).toHaveValue("service-1");
    const addService = screen.getByRole("button", { name: "Add another service" });
    expect(addService).toBeEnabled();
    fireEvent.click(addService);
    expect(await screen.findByText("1 proposal line staged")).toBeVisible();

    vi.mocked(priceBookApi.getPriceBook).mockResolvedValue({
      categories: [],
      tax_classifications: [],
      option_groups: [],
      options: [],
      service_items: [],
      versions: [],
      total_service_items: 0,
      limit: 500,
      offset: 0,
      costs_visible: false,
    });
    fireEvent.change(screen.getByLabelText("Search active Price Book services"), {
      target: { value: "toilet" },
    });
    await screen.findByText(/No active Price Book services match/);
    fireEvent.submit(
      screen.getByRole("button", { name: "Create immutable Estimate" }).closest("form")!,
    );

    await waitFor(() =>
      expect(priceBookApi.createCommercialSnapshot).toHaveBeenCalledWith(
        "service-1",
        expect.objectContaining({ quantity: "1" }),
      ),
    );
    expect(vi.mocked(estimatesApi.createEstimate).mock.calls[0][0]).toEqual(
      expect.objectContaining({
        lines: [
          expect.objectContaining({
            title: "Heating service",
            description: "Heating service",
          }),
        ],
      }),
    );
  });
});
