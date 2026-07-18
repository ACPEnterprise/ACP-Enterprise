import type { BrandConfiguration } from "./types";

export function applyBrandDocumentMetadata(
  brand: BrandConfiguration,
  target: Document = document,
): void {
  target.title = brand.applicationTitle;

  if (!brand.favicon) {
    return;
  }

  let favicon = target.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!favicon) {
    favicon = target.createElement("link");
    favicon.rel = "icon";
    target.head.append(favicon);
  }
  favicon.href = brand.favicon.href;
  if (brand.favicon.type) {
    favicon.type = brand.favicon.type;
  }
}
