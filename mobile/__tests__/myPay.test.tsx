import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import type { PayrollService } from "../src/api/payroll";
import { ApiFailure } from "../src/api/types";
import { MyPayScreen } from "../src/screens/MyPayScreen";

jest.mock("react-native-webview", () => ({ WebView: (props: object) => {
  const { View } = jest.requireActual("react-native");
  return <View testID="protected-statement-webview" {...props} />;
} }));

const statement = { id: "10000000-0000-4000-8000-000000000001", pay_period_id: "20000000-0000-4000-8000-000000000001", version: 2, currency: "USD", payment_status: "paid", ytd_status: "available", lifecycle: "issued", digest: "synthetic-digest", corrected: true };
function harness(connected = true) {
  let online = connected; let listener: ((value: boolean) => void) | undefined;
  const service: PayrollService = { status: jest.fn(async () => ({ statement_count: 1, current_statement_id: statement.id, current_pay_period_id: statement.pay_period_id, payment_status: "paid", ytd_status: "available", has_correction: true })), statements: jest.fn(async () => [statement]), artifact: jest.fn(async () => "<html><body>Synthetic protected statement</body></html>") };
  const network = { isConnected: jest.fn(async () => online), subscribe: jest.fn((next: (value: boolean) => void) => { listener = next; return () => undefined; }) };
  return { service, network, setConnected(value: boolean) { online = value; listener?.(value); } };
}

describe("employee My Pay", () => {
  it("renders own statement metadata, corrections, status, and secure artifact", async () => {
    const h = harness(); render(<MyPayScreen service={h.service} network={h.network} />);
    expect(await screen.findByText("Corrected pay statement")).toBeOnTheScreen();
    expect(screen.getByText("Year-to-date totals available")).toBeOnTheScreen();
    fireEvent.press(screen.getByLabelText("Securely view pay statement"));
    const viewer = await screen.findByTestId("protected-statement-webview");
    expect(h.service.artifact).toHaveBeenCalledWith(statement.id);
    expect(viewer.props.javaScriptEnabled).toBe(false); expect(viewer.props.domStorageEnabled).toBe(false); expect(viewer.props.cacheEnabled).toBe(false);
  });

  it("keeps empty, forbidden, expired, and server failure distinct", async () => {
    for (const [error, expected] of [[null, /No pay statements available/], ["forbidden", /not authorized/], ["unauthenticated", /session has expired/], ["unavailable", /temporarily unavailable/]] as const) {
      const h = harness(); (h.service.statements as jest.Mock).mockImplementation(async () => { if (error) throw new ApiFailure(error, error); return []; });
      const rendered = render(<MyPayScreen service={h.service} network={h.network} />);
      expect(await screen.findByText(expected)).toBeOnTheScreen(); rendered.unmount();
    }
  });

  it("marks cached metadata stale offline and prohibits artifact retrieval", async () => {
    const h = harness(); render(<MyPayScreen service={h.service} network={h.network} />); await screen.findByText("Corrected pay statement");
    act(() => h.setConnected(false));
    expect(await screen.findByText(/last confirmed and may be stale/)).toBeOnTheScreen();
    fireEvent.press(screen.getByLabelText("Securely view pay statement"));
    await waitFor(() => expect(screen.getByText(/Unable to open the protected statement/)).toBeOnTheScreen());
    expect(h.service.artifact).not.toHaveBeenCalled();
  });

  it("contains no other-employee selection, rates, tax, bank, or admin Payroll UI", async () => {
    const h = harness(); render(<MyPayScreen service={h.service} network={h.network} />); await screen.findByText("Corrected pay statement");
    expect(screen.queryByText(/employee id|hourly rate|salary|tax|bank|manage payroll|other employee/i)).not.toBeOnTheScreen();
  });
});
