import type { ReactNode } from "react";

import { Button, Card } from "../../ui";

interface ConfirmationDialogProps {
  title: string;
  confirmLabel: string;
  destructive?: boolean;
  pending: boolean;
  children: ReactNode;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmationDialog({
  title,
  confirmLabel,
  destructive = false,
  pending,
  children,
  onCancel,
  onConfirm,
}: ConfirmationDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-ui-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="mobile-confirmation-title"
    >
      <Card className="max-h-[90vh] w-full max-w-lg overflow-y-auto p-ui-5">
        <h2 id="mobile-confirmation-title" className="text-xl font-bold">
          {title}
        </h2>
        <div className="mt-ui-4 space-y-ui-3 text-sm">{children}</div>
        <div className="mt-ui-6 grid gap-ui-3">
          <Button
            fullWidth
            variant={destructive ? "destructive" : "primary"}
            size="large"
            loading={pending}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
          <Button
            fullWidth
            variant="outline"
            size="large"
            disabled={pending}
            onClick={onCancel}
          >
            Go back
          </Button>
        </div>
      </Card>
    </div>
  );
}
