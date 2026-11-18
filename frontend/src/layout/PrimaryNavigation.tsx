import { NavLink } from "react-router";

import { classNames } from "../ui/utilities/classNames";
import type { NavigationGroup } from "./types";

interface PrimaryNavigationProps {
  readonly groups: readonly NavigationGroup[];
  readonly onNavigate?: () => void;
}

export function PrimaryNavigation({ groups, onNavigate }: PrimaryNavigationProps) {
  return (
    <nav aria-label="Primary navigation" className="theme-primary-navigation min-w-0 flex-1 overflow-y-auto p-ui-3">
      <div className="flex flex-col gap-ui-5">
        {groups.map((group) => (
          <section aria-labelledby={`navigation-${group.id}`} key={group.id}>
            <h2
              id={`navigation-${group.id}`}
              className="theme-navigation-section-label mb-ui-2 px-ui-3 text-overline uppercase text-navigation-content/60"
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
                        title={`${item.label}, Coming Soon`}
                        className={classNames(
                          "flex min-h-11 min-w-0 cursor-not-allowed items-center gap-ui-3 rounded-md px-ui-3 text-body-s text-navigation-content/50",
                        )}
                      >
                        <Icon aria-hidden="true" className="size-[var(--icon-medium)] shrink-0" />
                        <span className="theme-navigation-item-label min-w-0 flex-1 whitespace-nowrap">{item.label}</span>
                        <span className="theme-navigation-soon-label shrink-0 text-[0.625rem] font-semibold uppercase tracking-wide">Soon</span>
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
                      aria-label={item.label}
                      title={item.label}
                      className={({ isActive }) => classNames(
                        "flex min-h-11 min-w-0 items-center gap-ui-3 rounded-md px-ui-3 text-body-s font-semibold text-navigation-content transition-colors hover:bg-surface-muted focus-visible:outline-offset-0 motion-reduce:transition-none",
                        isActive && "bg-navigation-active text-content-inverse",
                      )}
                    >
                      <Icon aria-hidden="true" className="size-[var(--icon-medium)] shrink-0" />
                      <span className="theme-navigation-item-label min-w-0 whitespace-nowrap">{item.label}</span>
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
