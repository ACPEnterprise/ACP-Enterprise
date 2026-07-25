import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { Button } from "../actions/Button";
import { Card } from "../surfaces/Card";

export interface ConfirmationDialogProps {
  readonly title: string;
  readonly description?: string;
  readonly confirmLabel: string;
  readonly cancelLabel?: string;
  readonly destructive?: boolean;
  readonly pending?: boolean;
  readonly initialFocus?: "cancel" | "confirm";
  readonly children?: ReactNode;
  readonly onCancel: () => void;
  readonly onConfirm: () => void;
}

const focusableSelector = [
  "button:not([disabled])",
  "a[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

export function ConfirmationDialog({
  cancelLabel = "Go back",
  children,
  confirmLabel,
  description,
  destructive = false,
  initialFocus = "cancel",
  onCancel,
  onConfirm,
  pending = false,
  title,
}: ConfirmationDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const onCancelRef = useRef(onCancel);
  const pendingRef = useRef(pending);

  useEffect(() => {
    onCancelRef.current = onCancel;
    pendingRef.current = pending;
  }, [onCancel, pending]);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    const applicationRoot = document.getElementById("root");
    const rootWasInert = applicationRoot?.hasAttribute("inert") ?? false;

    document.body.style.overflow = "hidden";
    applicationRoot?.setAttribute("inert", "");
    const initialTarget =
      initialFocus === "confirm" ? confirmRef.current : cancelRef.current;
    if (initialTarget && !initialTarget.disabled) initialTarget.focus();
    else dialogRef.current?.focus();

    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        if (!pendingRef.current) {
          event.preventDefault();
          onCancelRef.current();
        }
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;

      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(focusableSelector),
      );
      if (focusable.length === 0) {
        event.preventDefault();
        dialogRef.current.focus();
        return;
      }

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

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (!rootWasInert) applicationRoot?.removeAttribute("inert");
      previouslyFocused?.focus();
    };
  }, [initialFocus]);

  const keepFocusInside = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Tab" && !dialogRef.current?.contains(document.activeElement)) {
      event.preventDefault();
      cancelRef.current?.focus();
    }
  };

  return createPortal(
    <div className="safe-area-dialog fixed inset-0 z-[var(--layer-dialog)] grid place-items-center bg-[var(--semantic-scrim)]">
      <Card
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        onKeyDown={keepFocusInside}
        className="max-h-[calc(100dvh-var(--safe-area-top)-var(--safe-area-bottom)-2rem)] w-full max-w-lg overflow-y-auto overscroll-contain p-ui-4 sm:p-ui-6"
      >
        <h2 id={titleId} className="text-heading-s text-content">
          {title}
        </h2>
        {description && (
          <p id={descriptionId} className="mt-ui-2 text-body-s text-content-muted">
            {description}
          </p>
        )}
        {children && (
          <div className="mt-ui-4 min-w-0 space-y-ui-3 text-body-s text-content-secondary">
            {children}
          </div>
        )}
        <div className="mt-ui-6 grid gap-ui-3 sm:grid-cols-2">
          <Button
            ref={cancelRef}
            fullWidth
            size="large"
            variant="outline"
            disabled={pending}
            onClick={onCancel}
          >
            {cancelLabel}
          </Button>
          <Button
            ref={confirmRef}
            fullWidth
            size="large"
            variant={destructive ? "destructive" : "primary"}
            loading={pending}
            loadingLabel={`Processing ${confirmLabel}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </Card>
    </div>,
    document.body,
  );
}
