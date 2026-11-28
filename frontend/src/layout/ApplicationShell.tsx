import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Outlet, useLocation, useMatches, useNavigationType } from "react-router";

import { brandConfig } from "../branding/brandConfig";
import { AccessAgreementRoute } from "../routes/AccessAgreementRoute";
import { useCurrentAccessAgreement } from "../hooks/useAccessAgreement";
import { useAuth } from "../auth";
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
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const navigationTriggerRef = useRef<HTMLButtonElement>(null);
  const mobileNavigationRef = useRef<HTMLElement>(null);
  const workspaceRef = useRef<HTMLElement>(null);
  const { activeCompany, status } = useAuth();
  const agreement = useCurrentAccessAgreement(activeCompany?.id, status === "authenticated");
  const matches = useMatches();
  const location = useLocation();
  const navigationType = useNavigationType();
  const metadata = [...matches].reverse().find((match) => isShellHandle(match.handle))?.handle;
  const workspaceMetadata = isShellHandle(metadata) ? metadata.workspace : fallbackMetadata;
  const agreementRequired = agreement.data?.required && !agreement.data.accepted;

  const closeMobileNavigation = useCallback(() => {
    setMobileNavigationOpen(false);
    window.requestAnimationFrame(() => navigationTriggerRef.current?.focus({ preventScroll: true }));
  }, []);

  useEffect(() => {
    document.title = `${workspaceMetadata.pageTitle} | ${brandConfig.applicationTitle}`;
  }, [workspaceMetadata.pageTitle]);

  useEffect(() => {
    if (navigationType === "PUSH") workspaceRef.current?.focus({ preventScroll: true });
  }, [location.pathname, navigationType]);

  useEffect(() => {
    if (!mobileNavigationOpen) return undefined;
    const body = document.body;
    const documentElement = document.documentElement;
    const workspace = workspaceRef.current;
    const scrollPosition = window.scrollY;
    const previousBodyStyles = {
      overflow: body.style.overflow,
      position: body.style.position,
      top: body.style.top,
      width: body.style.width,
    };
    const previousDocumentOverflow = documentElement.style.overflow;
    const previousWorkspaceOverflow = workspace?.style.overflow;

    body.style.position = "fixed";
    body.style.top = `-${scrollPosition}px`;
    body.style.width = "100%";
    document.body.style.overflow = "hidden";
    documentElement.style.overflow = "hidden";
    if (workspace) workspace.style.overflow = "hidden";
    mobileNavigationRef.current
      ?.querySelector<HTMLElement>('button[aria-label="Close navigation"]')
      ?.focus({ preventScroll: true });

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeMobileNavigation();
      }
    };
    const keepFocusInNavigation = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || !mobileNavigationRef.current) return;
      const focusable = Array.from(
        mobileNavigationRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => !element.hasAttribute("hidden"));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const closeAtDesktopWidth = (event: MediaQueryListEvent) => {
      if (event.matches) setMobileNavigationOpen(false);
    };
    const desktopWidth = window.matchMedia("(min-width: 64rem)");

    window.addEventListener("keydown", closeOnEscape);
    window.addEventListener("keydown", keepFocusInNavigation);
    desktopWidth.addEventListener("change", closeAtDesktopWidth);
    return () => {
      body.style.overflow = previousBodyStyles.overflow;
      body.style.position = previousBodyStyles.position;
      body.style.top = previousBodyStyles.top;
      body.style.width = previousBodyStyles.width;
      documentElement.style.overflow = previousDocumentOverflow;
      if (workspace && previousWorkspaceOverflow !== undefined) {
        workspace.style.overflow = previousWorkspaceOverflow;
      }
      if (scrollPosition > 0) window.scrollTo(0, scrollPosition);
      window.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("keydown", keepFocusInNavigation);
      desktopWidth.removeEventListener("change", closeAtDesktopWidth);
    };
  }, [closeMobileNavigation, mobileNavigationOpen]);

  const mobileNavigation = mobileNavigationOpen
    ? createPortal(
        <>
          <button
            type="button"
            aria-label="Close navigation"
            className="theme-navigation-backdrop fixed inset-0 z-[var(--layer-navigation)] bg-[var(--semantic-overlay)] lg:hidden"
            onClick={closeMobileNavigation}
          />
          <Sidebar
            brand={brandConfig}
            mobile
            navigationRef={mobileNavigationRef}
            onClose={closeMobileNavigation}
            onNavigate={() => setMobileNavigationOpen(false)}
          />
        </>,
        document.body,
      )
    : null;

  if (agreementRequired && location.pathname !== "/access-agreement") {
    return <AccessAgreementRoute />;
  }

  return (
    <div
      className="theme-shell flex min-h-screen min-h-dvh bg-app-background text-content"
      data-mobile-navigation-open={mobileNavigationOpen || undefined}
      inert={mobileNavigationOpen ? true : undefined}
    >
      <SkipLink />
      <Sidebar
        brand={brandConfig}
      />
      <div aria-hidden="true" className="theme-viewport-backdrop" />
      {mobileNavigation}
      <div className="theme-shell-content flex min-h-screen min-h-dvh min-w-0 flex-1 flex-col">
        <ApplicationHeader
          brand={brandConfig}
          metadata={workspaceMetadata}
          navigationOpen={mobileNavigationOpen}
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
