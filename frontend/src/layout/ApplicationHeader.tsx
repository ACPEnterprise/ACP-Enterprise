import { Menu, Search } from "lucide-react";
import type { RefObject } from "react";
import { Link } from "react-router";

import type { BrandConfiguration } from "../branding/types";
import { useTheme } from "../theme/useTheme";
import { IconButton, Select, VisuallyHidden } from "../ui";
import { NotificationCenterRegion } from "./NotificationCenterRegion";
import type { WorkspaceMetadata } from "./types";

interface ApplicationHeaderProps {
  readonly brand: BrandConfiguration;
  readonly metadata: WorkspaceMetadata;
  readonly onOpenNavigation: () => void;
  readonly navigationTriggerRef: RefObject<HTMLButtonElement | null>;
}

export function ApplicationHeader({ brand, metadata, onOpenNavigation, navigationTriggerRef }: ApplicationHeaderProps) {
  const { preference, setPreference } = useTheme();

  return (
    <header className="sticky top-0 z-[var(--layer-sticky)] border-b border-stroke bg-header px-ui-4 py-ui-3 md:px-ui-6">
      <div className="flex min-h-14 items-center justify-between gap-ui-4">
        <div className="flex min-w-0 items-center gap-ui-3">
          <IconButton
            ref={navigationTriggerRef}
            icon={<Menu />}
            label="Open navigation"
            variant="ghost"
            onClick={onOpenNavigation}
            className="lg:hidden"
          />
          <div className="min-w-0">
            {metadata.breadcrumbs.length > 0 && (
              <nav aria-label="Breadcrumb" className="mb-ui-1 hidden sm:block">
                <ol className="flex flex-wrap items-center gap-ui-2 text-caption text-content-muted">
                  {metadata.breadcrumbs.map((breadcrumb, index) => {
                    const current = index === metadata.breadcrumbs.length - 1;
                    return (
                      <li key={`${breadcrumb.label}-${index}`} className="flex items-center gap-ui-2">
                        {index > 0 && <span aria-hidden="true">/</span>}
                        {!current && breadcrumb.path ? (
                          <Link to={breadcrumb.path} className="hover:text-content">{breadcrumb.label}</Link>
                        ) : (
                          <span aria-current={current ? "page" : undefined}>{breadcrumb.label}</span>
                        )}
                      </li>
                    );
                  })}
                </ol>
              </nav>
            )}
            <h1 className="truncate text-heading-m text-content">{metadata.pageTitle}</h1>
          </div>
        </div>

        <div className="flex items-center gap-ui-2">
          <IconButton icon={<Search />} label="Global search is not yet available" variant="ghost" disabled />
          <NotificationCenterRegion />
          <label className="relative">
            <VisuallyHidden>Theme preference</VisuallyHidden>
            <Select
              value={preference}
              onChange={(event) => setPreference(event.target.value as "light" | "dark" | "system")}
              aria-label="Theme preference"
              className="w-auto min-w-24 py-ui-2"
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </Select>
          </label>
          {brand.environment && <span className="hidden text-caption text-content-muted xl:inline">{brand.environment}</span>}
          <span className="hidden text-body-s text-content-muted md:inline">Account unavailable</span>
        </div>
      </div>
    </header>
  );
}
