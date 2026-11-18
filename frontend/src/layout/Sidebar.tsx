import { X } from "lucide-react";

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
  readonly onNavigate?: () => void;
  readonly onClose?: () => void;
}

export function Sidebar({
  brand,
  mobile = false,
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
      aria-label={mobile ? "Mobile application navigation" : "Application navigation"}
      className={mobile
        ? "theme-navigation safe-area-drawer fixed inset-y-0 left-0 z-[var(--layer-overlay)] flex h-dvh w-72 max-w-[calc(100vw-var(--space-8))] min-w-0 flex-col overflow-hidden border-r border-stroke bg-navigation shadow-lg"
        : "theme-navigation hidden w-64 min-w-64 shrink-0 flex-col overflow-hidden border-r border-stroke bg-navigation lg:flex"}
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
            className="absolute right-ui-2 top-ui-5"
          />
        )}
      </div>
      <PrimaryNavigation groups={visibleGroups} onNavigate={onNavigate} />
    </aside>
  );
}
