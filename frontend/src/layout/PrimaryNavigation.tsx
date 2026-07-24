import { NavLink } from "react-router";

import { classNames } from "../ui/utilities/classNames";
import type { NavigationGroup } from "./types";

interface PrimaryNavigationProps {
  readonly groups: readonly NavigationGroup[];
  readonly collapsed?: boolean;
  readonly onNavigate?: () => void;
}

export function PrimaryNavigation({ groups, collapsed = false, onNavigate }: PrimaryNavigationProps) {
  return (
    <nav aria-label="Primary navigation" className="flex-1 overflow-y-auto p-ui-3">
      <div className="flex flex-col gap-ui-5">
        {groups.map((group) => (
          <section aria-labelledby={`navigation-${group.id}`} key={group.id}>
            <h2
              id={`navigation-${group.id}`}
              className={collapsed ? "sr-only" : "mb-ui-2 px-ui-3 text-overline uppercase text-navigation-content/60"}
            >
              {group.label}
            </h2>
            <ul className="flex flex-col gap-ui-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                if (item.availability === "coming-soon") {
                  return (
                    <li key={item.id}>
                      <div
                        aria-disabled="true"
                        aria-label={`${item.label}, Coming Soon`}
                        className={classNames(
                          "flex min-h-11 cursor-not-allowed items-center rounded-md px-ui-3 text-body-s text-navigation-content/50",
                          collapsed ? "justify-center" : "gap-ui-3",
                        )}
                      >
                        <Icon aria-hidden="true" className="size-[var(--icon-medium)] shrink-0" />
                        {!collapsed && (
                          <>
                            <span className="min-w-0 flex-1 truncate">{item.label}</span>
                            <span className="text-[0.625rem] font-semibold uppercase tracking-wide">Soon</span>
                          </>
                        )}
                      </div>
                    </li>
                  );
                }
                return (
                  <li key={item.id}>
                    <NavLink
                      to={item.path}
                      end={item.path === "/"}
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
          </section>
        ))}
      </div>
    </nav>
  );
}
