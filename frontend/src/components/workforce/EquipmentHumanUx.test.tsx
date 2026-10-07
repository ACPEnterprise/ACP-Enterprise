import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as equipmentApi from "../../api/equipmentReadiness";
import { DailyEquipmentConfirmation } from "./DailyEquipmentConfirmation";
import { EquipmentAttentionPanel } from "./EquipmentAttentionPanel";
import { EquipmentChecklistSettingCard } from "./EquipmentChecklistSettingCard";

vi.mock("../../api/equipmentReadiness", async (loadOriginal) => ({
  ...await loadOriginal<typeof import("../../api/equipmentReadiness")>(),
  getEquipmentChecklistSetting: vi.fn(),
  setEquipmentChecklistSetting: vi.fn(),
  getEquipmentAttention: vi.fn(),
  confirmDailyEquipment: vi.fn(),
}));

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("Employee equipment human UX", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(equipmentApi.getEquipmentChecklistSetting).mockResolvedValue({ employee_id: "employee-1", equipment_checklist_requirement: "not_required" });
    vi.mocked(equipmentApi.setEquipmentChecklistSetting).mockImplementation(async (employee_id, equipment_checklist_requirement) => ({ employee_id, equipment_checklist_requirement }));
    vi.mocked(equipmentApi.getEquipmentAttention).mockResolvedValue([]);
    vi.mocked(equipmentApi.confirmDailyEquipment).mockResolvedValue({});
  });

  it("shows a simple governed checklist choice separate from vehicle assignment", async () => {
    renderWithQuery(<EquipmentChecklistSettingCard employeeId="employee-1" canManage />);
    expect(await screen.findByRole("radio", { name: "Not required" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "Required at clock-in" }));
    expect(equipmentApi.setEquipmentChecklistSetting).toHaveBeenCalledWith("employee-1", "required_at_clock_in");
    expect(screen.getByText(/Vehicle assignment is unavailable/)).toBeInTheDocument();
  });

  it("does not expose setting changes without management authority", async () => {
    renderWithQuery(<EquipmentChecklistSettingCard employeeId="employee-1" canManage={false} />);
    expect(await screen.findByRole("radio", { name: "Not required" })).toBeDisabled();
    expect(screen.getByText(/Management authority is required/)).toBeInTheDocument();
  });

  it("confirms the backend-provided equipment list before continuing to clock in", async () => {
    const onContinue = vi.fn().mockResolvedValue(undefined);
    renderWithQuery(<DailyEquipmentConfirmation employeeId="employee-1" workDate="2026-10-06" items={[{ catalog_item_id: "catalog-1", placement_id: "placement-1", display_name: "K-60 Drain Machine", default_state: "present_ready" }]} onContinue={onContinue} />);
    expect(screen.getByText("K-60 Drain Machine")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Confirm & Clock In" }));
    expect(vi.mocked(equipmentApi.confirmDailyEquipment).mock.calls[0]?.[0]).toEqual(expect.objectContaining({ employee_id: "employee-1", items: [expect.objectContaining({ state: "present_ready" })] }));
    expect(onContinue).toHaveBeenCalled();
  });

  it("uses human exception language and fails closed on a transfer needing more authority", async () => {
    renderWithQuery(<DailyEquipmentConfirmation employeeId="employee-1" workDate="2026-10-06" items={[{ catalog_item_id: "catalog-1", placement_id: "placement-1", display_name: "ProPress Tool", default_state: "present_ready" }]} onContinue={vi.fn()} />);
    await userEvent.selectOptions(screen.getByLabelText("ProPress Tool condition"), "transferred");
    expect(screen.getByRole("option", { name: "Missing / location unknown" })).toBeInTheDocument();
    expect(screen.getByText(/governed recipient or Location/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm & Clock In" })).toBeDisabled();
  });

  it("shows managers the canonical attention result and a truthful clear state", async () => {
    const view = renderWithQuery(<EquipmentAttentionPanel branchId="branch-1" authorized />);
    expect(await screen.findByText("No equipment issues requiring attention.")).toBeInTheDocument();
    view.unmount();
    renderWithQuery(<EquipmentAttentionPanel branchId="branch-1" authorized={false} />);
    expect(screen.queryByText(/equipment issues/)).not.toBeInTheDocument();
  });
});
