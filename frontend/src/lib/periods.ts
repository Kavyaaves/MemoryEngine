// Timeline "period" strings from the API: "2024" (year), "2024-06" (month) or "2024-06-14" (day).
// Pure helpers to parse, format and turn them into date ranges.

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** 1 → "Jan" */
export function monthName(month: number): string {
  return MONTH_NAMES[month - 1] ?? String(month);
}

/** "2024" → "2024", "2024-06" → "Jun 2024", "2024-06-14" → "Jun 14, 2024" */
export function formatPeriod(period: string): string {
  const [year, month, day] = period.split("-");
  if (month && day) return `${monthName(Number(month))} ${Number(day)}, ${year}`;
  if (month) return `${monthName(Number(month))} ${year}`;
  return year ?? period;
}

/** "2024-06…" → { year: 2024, month: 6 }; null when the string has no month. */
export function parseMonth(period: string): { year: number; month: number } | null {
  const match = /^(\d{4})-(\d{2})/.exec(period);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]) };
}

export function daysInMonth(year: number, month: number): number {
  // Day 0 of the next month is the last day of this one.
  return new Date(year, month, 0).getDate();
}

/** "2024-02" → { start: "2024-02-01", end: "2024-02-29" } — both inclusive, as the API expects. */
export function monthRange(month: string): { start: string; end: string } {
  const parsed = parseMonth(month);
  if (!parsed) return { start: month, end: month };
  const monthText = String(parsed.month).padStart(2, "0");
  const lastDay = String(daysInMonth(parsed.year, parsed.month)).padStart(2, "0");
  return { start: `${parsed.year}-${monthText}-01`, end: `${parsed.year}-${monthText}-${lastDay}` };
}
