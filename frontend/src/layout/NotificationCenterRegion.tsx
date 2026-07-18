import { Bell } from "lucide-react";

import { IconButton } from "../ui";

export function NotificationCenterRegion() {
  return (
    <div aria-label="Notification Center">
      <IconButton
        icon={<Bell />}
        label="Notification Center is not yet available"
        variant="ghost"
        disabled
      />
    </div>
  );
}
