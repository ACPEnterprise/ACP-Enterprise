import type { ThemePreference } from "../theme/types";

export interface BrandAsset {
  readonly src: string;
  readonly alt: string;
}

export interface FaviconAsset {
  readonly href: string;
  readonly type?: string;
}

export interface BrandConfiguration {
  readonly logo?: BrandAsset;
  readonly logoSmall?: BrandAsset;
  readonly wordmark: string;
  readonly productName: string;
  readonly companyName?: string;
  readonly tagline?: string;
  readonly applicationTitle: string;
  readonly favicon?: FaviconAsset;
  readonly defaultTheme: ThemePreference;
  readonly environment?: string;
  readonly supportEmail?: string;
  readonly supportWebsite?: string;
}
