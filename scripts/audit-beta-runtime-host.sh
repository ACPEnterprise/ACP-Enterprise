#!/bin/sh
set -eu

backup_root=${BACKUP_ROOT:-/opt/acp-enterprise/backups}
max_backup_age_hours=${MAX_BACKUP_AGE_HOURS:-26}
disk_warning_percent=${DISK_WARNING_PERCENT:-85}
disk_blocker_percent=${DISK_BLOCKER_PERCENT:-90}

systemctl is-active --quiet caddy

disk_percent=$(df -P / | awk 'NR == 2 {gsub(/%/, "", $5); print $5}')
if [ "$disk_percent" -ge "$disk_blocker_percent" ]; then
  echo "BLOCKED: root disk utilization is $disk_percent%." >&2
  exit 1
fi
if [ "$disk_percent" -ge "$disk_warning_percent" ]; then
  echo "WARNING: root disk utilization is $disk_percent%." >&2
fi

unhealthy=$(docker ps --format '{{.Names}}|{{.Status}}' | grep -E '\(unhealthy\)|Restarting' || true)
if [ -n "$unhealthy" ]; then
  echo "BLOCKED: unhealthy or restarting runtime containers:" >&2
  printf '%s\n' "$unhealthy" >&2
  exit 1
fi

latest_backup=$(find "$backup_root" -type f -name '*.dump' -printf '%T@ %m %p\n' 2>/dev/null \
  | sort -nr | head -1)
if [ -z "$latest_backup" ]; then
  echo "BLOCKED: no Preview database backup exists under $backup_root." >&2
  exit 1
fi

backup_epoch=$(printf '%s\n' "$latest_backup" | awk '{printf "%.0f", $1}')
backup_mode=$(printf '%s\n' "$latest_backup" | awk '{print $2}')
backup_path=$(printf '%s\n' "$latest_backup" | cut -d' ' -f3-)
backup_age_hours=$((($(date +%s) - backup_epoch) / 3600))
if [ "$backup_age_hours" -gt "$max_backup_age_hours" ]; then
  echo "BLOCKED: newest Preview backup is $backup_age_hours hours old." >&2
  exit 1
fi
if [ "$backup_mode" != "600" ]; then
  echo "BLOCKED: newest Preview backup mode is $backup_mode instead of 600." >&2
  exit 1
fi

scripts/verify-beta-connectivity.sh
echo "root_disk_percent=$disk_percent"
echo "latest_preview_backup=$backup_path"
echo "latest_preview_backup_age_hours=$backup_age_hours"
echo "beta_runtime_host=healthy"

