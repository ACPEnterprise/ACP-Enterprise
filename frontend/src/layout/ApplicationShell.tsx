import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation, useMatches, useNavigationType } from "react-router";

import { brandConfig } from "../branding/brandConfig";
import { AIWorkspace } from "./AIWorkspace";
import { ApplicationHeader } from "./ApplicationHeader";
import { Sidebar } from "./Sidebar";
import { SkipLink } from "./SkipLink";
import type { ShellRouteHandle, WorkspaceMetadata } from "./types";
import { Workspace } from "./Workspace";

const fallbackMetadata: WorkspaceMetadata = {
  pageTitle: "ACP Enterprise",
  breadcrumbs: [],
};

function isShellHandle(value: unknown): value is ShellRouteHandle {
  return Boolean(
    value &&
      typeof value === "object" &&
      "workspace" in value &&
      typeof value.workspace === "object",
  );
}

export function ApplicationShell() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const navigationTriggerRef = useRef<HTMLButtonElement>(null);
  const workspaceRef = useRef<HTMLElement>(null);
  const matches = useMatches();
  const location = useLocation();
  const navigationType = useNavigationType();
  const metadata = [...matches].reverse().find((match) => isShellHandle(match.handle))?.handle;
  const workspaceMetadata = isShellHandle(metadata) ? metadata.workspace : fallbackMetadata;

  useEffect(() => {
    document.title = `${workspaceMetadata.pageTitle} | ${brandConfig.applicationTitle}`;
  }, [workspaceMetadata.pageTitle]);

  useEffect(() => {
    if (navigationType === "PUSH") workspaceRef.current?.focus({ preventScroll: true });
  }, [location.pathname, navigationType]);

  useEffect(() => {
    if (!mobileNavigationOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileNavigationOpen(false);
        navigationTriggerRef.current?.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [mobileNavigationOpen]);

  const closeMobileNavigation = () => {
    setMobileNavigationOpen(false);
    navigationTriggerRef.current?.focus();
  };

  return (
    <div className="flex min-h-screen bg-app-background text-content">
      <SkipLink />
      <Sidebar
        brand={brandConfig}
        collapsed={collapsed}
        onCollapseToggle={() => setCollapsed((value) => !value)}
      />
      {mobileNavigationOpen && (
        <>
          <button
            type="button"
            aria-label="Close navigation"
            className="fixed inset-0 z-[var(--layer-navigation)] bg-[var(--semantic-overlay)] lg:hidden"
            onClick={closeMobileNavigation}
          />
          <div className="lg:hidden">
            <Sidebar
              brand={brandConfig}
              mobile
              onClose={closeMobileNavigation}
              onNavigate={() => setMobileNavigationOpen(false)}
            />
          </div>
        </>
      )}
      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        <ApplicationHeader
          brand={brandConfig}
          metadata={workspaceMetadata}
          navigationTriggerRef={navigationTriggerRef}
          onOpenNavigation={() => setMobileNavigationOpen(true)}
        />
        <div className="flex min-h-0 flex-1">
          <Workspace ref={workspaceRef}>
            <Outlet />
          </Workspace>
          <AIWorkspace />
        </div>
      </div>
    </div>
  );
}
