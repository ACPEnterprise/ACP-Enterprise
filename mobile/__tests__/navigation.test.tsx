import { render, screen } from "@testing-library/react-native";
import { HomeScreen } from "../src/screens/HomeScreen";
import { SignInScreen } from "../src/screens/SignInScreen";
import { TimeScreen } from "../src/screens/TimeScreen";
describe("application shell", () => {
  it("boots an unauthenticated sign-in foundation", () => { render(<SignInScreen />); expect(screen.getByText("ACP Employee")).toBeOnTheScreen(); });
  it("renders authenticated Home without business fixtures", () => { render(<HomeScreen />); expect(screen.getByText("Home")).toBeOnTheScreen(); expect(screen.queryByText(/job|hours|alert|schedule/i)).not.toBeOnTheScreen(); });
  it("renders the native My Time route boundary", () => { render(<TimeScreen />); expect(screen.getByText("My Time")).toBeOnTheScreen(); });
});
