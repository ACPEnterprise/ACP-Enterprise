import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { BrandConfiguration } from "../branding/types";
import { BrandRegion } from "./BrandRegion";

const brand: BrandConfiguration = {
  wordmark: "ACP Enterprise",
  productName: "ACP Enterprise",
  applicationTitle: "ACP Enterprise",
  defaultTheme: "dark",
};

describe("BrandRegion", () => {
  it("uses configured text fallback without inventing company identity", () => {
    render(<BrandRegion brand={brand} />);
    expect(screen.getByText("ACP Enterprise")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders configured identity and environment independently", () => {
    render(<BrandRegion brand={{ ...brand, logo: { src: "/logo.svg", alt: "Company logo" }, companyName: "Example Services", environment: "Preview" }} />);
    expect(screen.getByRole("img", { name: "Company logo" })).toBeInTheDocument();
    expect(screen.getByText("Example Services")).toBeInTheDocument();
    expect(screen.getByText("Preview")).toBeInTheDocument();
  });
});
