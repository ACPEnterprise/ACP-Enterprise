import { act, render } from "@testing-library/react-native";
import { AppState, Text } from "react-native";
import { PrivacyShield } from "../src/components/PrivacyShield";

describe("signed beta readiness", () => {
  it("obscures application content while the app is inactive", () => {
    let listener: ((state: "active" | "background") => void) | undefined;
    Object.assign(AppState, { currentState: "active" });
    jest.spyOn(AppState, "addEventListener").mockImplementation((_, next) => {
      listener = next as typeof listener;
      return { remove: jest.fn() } as never;
    });
    const view = render(<PrivacyShield><Text>Authenticated content</Text></PrivacyShield>);
    expect(view.queryByLabelText("ACP Employee protected")).toBeNull();
    act(() => listener?.("background"));
    expect(view.getByLabelText("ACP Employee protected")).toBeTruthy();
    act(() => listener?.("active"));
    expect(view.queryByLabelText("ACP Employee protected")).toBeNull();
  });
});
