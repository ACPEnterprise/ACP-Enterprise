import type { BrandConfiguration } from "../branding/types";
import { Badge, Stack } from "../ui";

interface BrandRegionProps {
  readonly brand: BrandConfiguration;
  readonly compact?: boolean;
}

export function BrandRegion({ brand, compact = false }: BrandRegionProps) {
  const asset = compact ? (brand.logoSmall ?? brand.logo) : brand.logo;
  const fallback = brand.wordmark || brand.productName;

  return (
    <div className="flex min-h-20 items-center gap-ui-3 border-b border-stroke px-ui-4">
      {asset ? (
        <img src={asset.src} alt={asset.alt} className="size-10 shrink-0 object-contain" />
      ) : (
        <div aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-lg bg-action-primary text-heading-s font-bold text-content-inverse">
          {fallback.slice(0, 1).toUpperCase()}
        </div>
      )}
      {!compact && (
        <Stack space="none" className="min-w-0">
          <div className="flex flex-wrap items-center gap-ui-2">
            <span className="truncate text-heading-s text-navigation-content">{fallback}</span>
            {brand.environment && <Badge variant="information">{brand.environment}</Badge>}
          </div>
          {brand.companyName && <span className="truncate text-body-s text-content-muted">{brand.companyName}</span>}
          {brand.tagline && <span className="truncate text-caption text-content-muted">{brand.tagline}</span>}
        </Stack>
      )}
    </div>
  );
}
