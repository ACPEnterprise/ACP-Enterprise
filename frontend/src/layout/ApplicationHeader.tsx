import { CircleCheck, LogOut, Menu, Search } from "lucide-react";
import type { RefObject } from "react";
import { Link } from "react-router";

import type { BrandConfiguration } from "../branding/types";
import { useAuth } from "../auth";
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
  const { activeCompany, signOut, user } = useAuth();

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
          <div className="hidden text-right xl:block">
            {user && <p className="text-body-s font-semibold text-content">Welcome, {user.first_name}</p>}
            {activeCompany && <p className="text-caption text-content-muted">{activeCompany.name}</p>}
          </div>
          <span
            className="hidden items-center gap-ui-1 rounded-[var(--radius-round)] border border-stroke px-ui-3 py-ui-2 text-caption font-semibold text-content-secondary sm:inline-flex"
            role="status"
            title="The authenticated Command Center interface is available. This does not describe providers or workers."
          >
            <CircleCheck aria-hidden="true" className="size-4 text-status-success" />
            Command Center Online
          </span>
          <div className="hidden sm:contents">
            <IconButton icon={<Search />} label="Global search is not yet available" variant="ghost" disabled />
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
          {user && <span className="sr-only">Signed in as {user.display_name}</span>}
          <IconButton icon={<LogOut />} label="Sign out" variant="ghost" onClick={() => void signOut()} />
        </div>
      </div>
    </header>
  );
}
