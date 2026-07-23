import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DispatchWorkspaceLayout } from "./DispatchWorkspaceLayout";

describe("DispatchWorkspaceLayout", () => {
  it("keeps the workforce extension absent until authoritative data exists", () => {
    render(<DispatchWorkspaceLayout appointments={<section>Appointments queue</section>} jobs={<section>Jobs queue</section>} />);
    expect(screen.getByText("Appointments queue")).toBeInTheDocument();
    expect(screen.getByText("Jobs queue")).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Workforce recommendations" })).not.toBeInTheDocument();
  });
  it("provides an explicit future workforce composition boundary", () => {
    render(<DispatchWorkspaceLayout appointments={<section>Appointments queue</section>} jobs={<section>Jobs queue</section>} workforce={<div>Authoritative capability profiles</div>} />);
    expect(screen.getByRole("complementary", { name: "Workforce recommendations" })).toHaveTextContent("Authoritative capability profiles");
  });
});
