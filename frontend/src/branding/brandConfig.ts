import type { BrandConfiguration } from "./types";

/**
 * Platform defaults. A deployment may replace this object with its own company
 * identity without changing application or design-system components.
 */
export const brandConfig = {
  wordmark: "ACP ENTERPRISE",
  productName: "ACP Enterprise",
  applicationTitle: "ACP Enterprise Command Center",
  tagline: "COMMAND CENTER",
  favicon: {
    href: "/favicon.svg",
    type: "image/svg+xml",
  },
  defaultTheme: "dark",
} as const satisfies BrandConfiguration;
