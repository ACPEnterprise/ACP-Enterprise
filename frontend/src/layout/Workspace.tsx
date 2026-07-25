import { forwardRef, type ReactNode } from "react";

interface WorkspaceProps {
  readonly children: ReactNode;
}

export const Workspace = forwardRef<HTMLElement, WorkspaceProps>(function Workspace({ children }, ref) {
  return (
    <main
      ref={ref}
      id="main-workspace"
      tabIndex={-1}
      className="safe-area-workspace min-w-0 flex-1 overflow-y-auto bg-app-background focus:outline-none"
    >
      <div className="mx-auto w-full max-w-[var(--content-wide)]">{children}</div>
    </main>
  );
});
