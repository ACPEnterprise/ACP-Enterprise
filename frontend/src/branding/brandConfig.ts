import type { BrandConfiguration } from "./types";

/**
 * Platform defaults. A deployment may replace this object with its own company
 * identity without changing application or design-system components.
 */
export const brandConfig = {
  wordmark: "ACP Enterprise",
  productName: "ACP Enterprise",
  applicationTitle: "ACP Enterprise",
  favicon: {
    href: "/favicon.svg",
    type: "image/svg+xml",
  },
  defaultTheme: "dark",
} as const satisfies BrandConfiguration;
