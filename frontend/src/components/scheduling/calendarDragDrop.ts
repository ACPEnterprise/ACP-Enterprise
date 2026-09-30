export function quarterHourDropMinute(
  operatingStartMinute: number,
  visibleMinutes: number,
  pointerOffset: number,
): number {
  const bounded = Math.max(0, Math.min(visibleMinutes, pointerOffset));
  return Math.round((operatingStartMinute + bounded) / 15) * 15;
}
