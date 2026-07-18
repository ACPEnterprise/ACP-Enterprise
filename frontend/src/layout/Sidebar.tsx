import { PanelLeftClose, PanelLeftOpen, X } from "lucide-react";

import type { BrandConfiguration } from "../branding/types";
import { IconButton } from "../ui";
import { BrandRegion } from "./BrandRegion";
import { availableNavigation } from "./navigation";
import { PrimaryNavigation } from "./PrimaryNavigation";

interface SidebarProps {
  readonly brand: BrandConfiguration;
  readonly collapsed?: boolean;
  readonly mobile?: boolean;
  readonly onCollapseToggle?: () => void;
  readonly onNavigate?: () => void;
  readonly onClose?: () => void;
}

export function Sidebar({
  brand,
  collapsed = false,
  mobile = false,
  onCollapseToggle,
  onNavigate,
  onClose,
}: SidebarProps) {
  return (
    <aside
      aria-label={mobile ? "Mobile application navigation" : "Application navigation"}
      className={mobile
        ? "fixed inset-y-0 left-0 z-[var(--layer-overlay)] flex w-72 flex-col border-r border-stroke bg-navigation shadow-lg"
        : `hidden shrink-0 flex-col border-r border-stroke bg-navigation lg:flex ${collapsed ? "w-20" : "w-72"}`}
    >
      <div className="relative">
        <BrandRegion brand={brand} compact={collapsed} />
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
      <PrimaryNavigation items={availableNavigation} collapsed={collapsed} onNavigate={onNavigate} />
      {!mobile && (
        <div className="border-t border-stroke p-ui-3">
          <IconButton
            icon={collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            label={collapsed ? "Expand navigation" : "Collapse navigation"}
            variant="ghost"
            onClick={onCollapseToggle}
          />
        </div>
      )}
    </aside>
  );
}
