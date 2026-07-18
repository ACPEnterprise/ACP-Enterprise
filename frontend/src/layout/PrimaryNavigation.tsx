import { NavLink } from "react-router";

import { classNames } from "../ui/utilities/classNames";
import type { NavigationItem } from "./types";

interface PrimaryNavigationProps {
  readonly items: readonly NavigationItem[];
  readonly collapsed?: boolean;
  readonly onNavigate?: () => void;
}

export function PrimaryNavigation({ items, collapsed = false, onNavigate }: PrimaryNavigationProps) {
  return (
    <nav aria-label="Primary navigation" className="flex-1 p-ui-3">
      <ul className="flex flex-col gap-ui-1">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.id}>
              <NavLink
                to={item.path}
                onClick={onNavigate}
                aria-label={collapsed ? item.label : undefined}
                className={({ isActive }) => classNames(
                  "flex min-h-11 items-center rounded-md px-ui-3 text-body-s font-semibold text-navigation-content transition-colors hover:bg-surface-muted focus-visible:outline-offset-0 motion-reduce:transition-none",
                  collapsed ? "justify-center" : "gap-ui-3",
                  isActive && "bg-navigation-active text-content-inverse",
                )}
              >
                <Icon aria-hidden="true" className="size-[var(--icon-medium)] shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
