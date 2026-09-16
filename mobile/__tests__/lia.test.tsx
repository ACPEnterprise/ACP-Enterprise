import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { ApiFailure } from "../src/api/types";
import { LiaScreen } from "../src/screens/LiaScreen";
import { createLiaService } from "../src/api/lia";
import type { LiaResponse, LiaService } from "../src/api/lia";

const response: LiaResponse = {
  request_id: "10000000-0000-4000-8000-000000000001", conversation_id: "20000000-0000-4000-8000-000000000001", classification: "KNOWN", authority: "ACP_AUTHORITATIVE", answer: "Your next assigned appointment is synthetic.", evidence: [{ domain: "employee-operations", label: "My authorized assigned work", authority: "EMPLOYEE.DAY.v1", observed_at: "2026-09-16T12:00:00Z", freshness: "CURRENT_QUERY", evidence_digest: "a".repeat(64), branch_ids: [], limitations: ["Only your active assignments are included."] }], limitations: [], navigation: [], completeness: "COMPLETE_FOR_EMPLOYEE_SAFE_ADAPTERS", freshness: "CURRENT_QUERY", provider: "deterministic-acp", provider_version: "v1", policy_version: "LIA.EMPLOYEE_SAFE.v1", evidence_digest: "a".repeat(64), authorization_version: 1, company_id: "30000000-0000-4000-8000-000000000001", branch_ids: [], source_systems: ["employee-operations"], missing_evidence: [], safe_next_action: "Open My Day", as_of: "2026-09-16T12:00:00Z", generated_at: "2026-09-16T12:00:00Z", temporal: null,
};
function service() { return { ask: jest.fn(async () => response) } satisfies LiaService; }

describe("employee-safe Mobile LIA", () => {
  it("uses only the employee-safe endpoint", async () => { const client = { request: jest.fn(async () => response) }; await createLiaService(client as never).ask("What is my next job?"); const calls = client.request.mock.calls as unknown[][]; expect(calls[0]?.[0]).toBe("/api/v1/lia/employee/ask"); expect(calls.some(([path]) => path === "/api/v1/lia/ask")).toBe(false); });
  it("submits through the employee-safe service and preserves conversation continuity", async () => {
    const lia = service(); render(<LiaScreen service={lia} />);
    fireEvent.changeText(screen.getByLabelText("Ask LIA a question"), "What is my next job?"); fireEvent.press(screen.getByLabelText("Send question to Employee-safe LIA"));
    expect(await screen.findByText(response.answer)).toBeOnTheScreen();
    expect(lia.ask).toHaveBeenCalledWith("What is my next job?", undefined);
    fireEvent.changeText(screen.getByLabelText("Ask LIA a question"), "And the next one?"); fireEvent.press(screen.getByLabelText("Send question to Employee-safe LIA"));
    await waitFor(() => expect(lia.ask).toHaveBeenLastCalledWith("And the next one?", response.conversation_id));
  });
  it("renders compact provenance and expandable evidence", async () => { const lia = service(); render(<LiaScreen service={lia} />); fireEvent.changeText(screen.getByLabelText("Ask LIA a question"), "What is my next job?"); fireEvent.press(screen.getByLabelText("Send question to Employee-safe LIA")); await screen.findByText(/CURRENT QUERY/); fireEvent.press(screen.getByLabelText("Show LIA evidence")); expect(await screen.findByText(/Source:.*EMPLOYEE\.DAY\.v1/)).toBeOnTheScreen(); });
  it("keeps authorization, network, and malformed responses safe", async () => {
    for (const [error, expected] of [[new ApiFailure("forbidden", "denied"), /not available with your current Employee permissions/], [new ApiFailure("offline", "offline"), /offline/], [new ApiFailure("malformed_response", "bad"), /unavailable response/] ] as const) { const lia = service(); lia.ask.mockRejectedValueOnce(error); const view = render(<LiaScreen service={lia} />); fireEvent.changeText(screen.getByLabelText("Ask LIA a question"), "What is my next job?"); fireEvent.press(screen.getByLabelText("Send question to Employee-safe LIA")); expect(await screen.findByText(expected)).toBeOnTheScreen(); view.unmount(); }
  });
});
