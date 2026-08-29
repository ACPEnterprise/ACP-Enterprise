import { safeLogger } from "../src/diagnostics/safeLogger";
describe("safe diagnostics", () => {
  it("redacts protected data", () => { const spy = jest.spyOn(console, "info").mockImplementation(); safeLogger.info("test", { accessToken: "must-not-appear", status: 401 }); expect(spy).toHaveBeenCalledWith("test", { accessToken: "[REDACTED]", status: 401 }); expect(JSON.stringify(spy.mock.calls)).not.toContain("must-not-appear"); });
});
