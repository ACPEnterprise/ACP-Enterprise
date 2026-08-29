import { render, screen } from "@testing-library/react-native";
import { HomeScreen } from "../src/screens/HomeScreen";
import { SignInScreen } from "../src/screens/SignInScreen";
import { TimeScreen } from "../src/screens/TimeScreen";
import type { TimekeepingService } from "../src/api/timekeeping";
const state = { state: "not_clocked_in", last_action: null, occurred_at: null, server_observed_at: "2026-08-28T12:00:00Z", elapsed_seconds: null } as const;
const service: TimekeepingService = { state: async () => state, timecard: async () => ({ employee_id: "synthetic", punch_state: state, pay_period: null, entries: [] }), punch: jest.fn() };
const network = { isConnected: async () => true, subscribe: () => () => undefined };
describe("application shell", () => {
  it("boots an unauthenticated sign-in foundation", () => { render(<SignInScreen />); expect(screen.getByText("ACP Employee")).toBeOnTheScreen(); });
  it("renders authenticated Home without business fixtures", () => { render(<HomeScreen />); expect(screen.getByText("Home")).toBeOnTheScreen(); expect(screen.queryByText(/job|hours|alert|schedule/i)).not.toBeOnTheScreen(); });
  it("renders the native My Time route boundary", async () => { render(<TimeScreen service={service} network={network} canPunch />); expect(screen.getByText("My Time")).toBeOnTheScreen(); expect(await screen.findByText("Clock In")).toBeOnTheScreen(); });
});
