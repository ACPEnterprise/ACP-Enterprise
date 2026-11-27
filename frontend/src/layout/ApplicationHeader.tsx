import { CircleCheck, LogOut, Menu, Search, UserRound } from "lucide-react";
import { useCallback, useState, type RefObject } from "react";
import { Link } from "react-router";

import type { BrandConfiguration } from "../branding/types";
import { useAuth } from "../auth";
import { useTheme } from "../theme/useTheme";
import { IconButton, Select, VisuallyHidden } from "../ui";
import { GlobalSearchDialog } from "../components/search/GlobalSearchDialog";
import { NotificationCenterRegion } from "./NotificationCenterRegion";
import type { WorkspaceMetadata } from "./types";

interface ApplicationHeaderProps {
  readonly brand: BrandConfiguration;
  readonly metadata: WorkspaceMetadata;
  readonly navigationOpen?: boolean;
  readonly onOpenNavigation: () => void;
  readonly navigationTriggerRef: RefObject<HTMLButtonElement | null>;
}

export function ApplicationHeader({ brand, metadata, navigationOpen = false, onOpenNavigation, navigationTriggerRef }: ApplicationHeaderProps) {
  const { preference, setPreference } = useTheme();
  const { activeCompany, signOut, user } = useAuth();
  const [searchOpen, setSearchOpen] = useState(false);
  const closeSearch = useCallback(() => setSearchOpen(false), []);

  return (
    <header className="theme-header safe-area-header sticky top-0 z-[var(--layer-sticky)] border-b border-stroke bg-header">
      <div className="flex min-h-14 items-center justify-between gap-ui-4">
        <div className="flex min-w-0 items-center gap-ui-3">
          <IconButton
            ref={navigationTriggerRef}
            icon={<Menu />}
            label="Open navigation"
            variant="ghost"
            onClick={onOpenNavigation}
            aria-controls="mobile-application-navigation"
            aria-expanded={navigationOpen}
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
          <div className="hidden text-right xl:block">
            {user && <p className="text-body-s font-semibold text-content">Welcome, {user.first_name}</p>}
            {activeCompany && <p className="text-caption text-content-muted">{activeCompany.name}</p>}
          </div>
          <span
            className="hidden items-center gap-ui-1 rounded-[var(--radius-round)] border border-stroke px-ui-3 py-ui-2 text-caption font-semibold text-content-secondary sm:inline-flex"
            role="status"
            title="Your authenticated ACP session is active. Individual product and provider readiness is shown within each workspace."
          >
            <CircleCheck aria-hidden="true" className="size-4 text-status-success" />
            Authenticated session
          </span>
          <div className="hidden sm:contents">
            <IconButton icon={<Search />} label="Global search" variant="ghost" onClick={() => setSearchOpen(true)} />
            <NotificationCenterRegion />
          </div>
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
          <Link
            to="/account/security"
            className="inline-flex items-center gap-ui-2 rounded-[var(--radius-control)] px-ui-2 py-ui-2 text-body-s font-semibold text-content-secondary hover:bg-surface-muted hover:text-content focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action-primary"
          >
            <UserRound aria-hidden="true" className="size-4" />
            <span className="hidden sm:inline">Account</span>
            <span className="sr-only">Account and security</span>
          </Link>
          {user && <span className="sr-only">Signed in as {user.display_name}</span>}
          <IconButton icon={<LogOut />} label="Sign out" variant="ghost" onClick={() => void signOut()} />
        </div>
      </div>
      {searchOpen && <GlobalSearchDialog onClose={closeSearch} />}
    </header>
  );
}
