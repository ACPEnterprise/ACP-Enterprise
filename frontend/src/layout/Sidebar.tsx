import { X } from "lucide-react";
import type { RefObject } from "react";

import type { BrandConfiguration } from "../branding/types";
import { IconButton } from "../ui";
import { BrandRegion } from "./BrandRegion";
import { navigationGroups } from "./navigation";
import { PrimaryNavigation } from "./PrimaryNavigation";
import { useAdministrationAccess } from "../features/administration/hooks";
import { useEffectivePermissions } from "../auth/usePermissions";
import { isFieldTechnicianProfile } from "../auth/authorizationProfiles";

interface SidebarProps {
  readonly brand: BrandConfiguration;
  readonly mobile?: boolean;
  readonly navigationRef?: RefObject<HTMLElement | null>;
  readonly onNavigate?: () => void;
  readonly onClose?: () => void;
}

export function Sidebar({
  brand,
  mobile = false,
  navigationRef,
  onNavigate,
  onClose,
}: SidebarProps) {
  const administrationAccess = useAdministrationAccess();
  const permissions = useEffectivePermissions();
  const fieldTechnician = isFieldTechnicianProfile(permissions);
  const fieldNavigationIds = new Set(["technician", "my-schedule", "workday", "my-jobs"]);
  const visibleGroups = navigationGroups.map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (item.id === "administration" && !administrationAccess.isSuccess) return false;
      const requiredPermission = "requiredPermission" in item
        ? item.requiredPermission
        : undefined;
      return (
        (!fieldTechnician || fieldNavigationIds.has(item.id)) &&
        (!requiredPermission || permissions.has(requiredPermission))
      );
    }),
  }))
    .filter((group) => group.items.length > 0);
  return (
    <aside
      ref={navigationRef}
      id={mobile ? "mobile-application-navigation" : undefined}
      aria-label={mobile ? "Mobile application navigation" : "Application navigation"}
      aria-modal={mobile ? true : undefined}
      role={mobile ? "dialog" : undefined}
      className={mobile
        ? "theme-navigation theme-navigation-mobile safe-area-drawer flex flex-col overflow-hidden border-r border-stroke shadow-lg lg:hidden"
        : "theme-navigation theme-navigation-desktop hidden shrink-0 flex-col overflow-hidden border-r border-stroke lg:flex"}
    >
      <div className="relative">
        <BrandRegion brand={brand} />
        {mobile && (
          <IconButton
            icon={<X />}
            label="Close navigation"
            autoFocus
            variant="ghost"
            size="small"
            onClick={onClose}
            className="theme-navigation-close absolute right-ui-2 top-ui-5"
          />
        )}
      </div>
      <PrimaryNavigation groups={visibleGroups} onNavigate={onNavigate} />
    </aside>
  );
}
