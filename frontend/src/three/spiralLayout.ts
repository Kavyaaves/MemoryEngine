// Pure math for the 3D Life explorer (no React, no three.js): where each month column and day sphere goes.
// Time runs along a flat spiral, one turn per year starting at 12 o'clock with January;
// a column's height shows how many memories that month has.
import type { TimelineBucket } from "@/types/api";
import { daysInMonth, parseMonth } from "@/lib/periods";
import { dominantSource, sourceMeta } from "@/lib/sources";

const INNER_RADIUS = 5; // radius where the first year starts
const YEAR_SPACING = 2.6; // how far each yearly turn is from the previous one
const MAX_COLUMN_HEIGHT = 6;
const MIN_COLUMN_HEIGHT = 0.12;
/** Radius of the ring of day spheres floating above a selected month. */
export const DAY_RING_RADIUS = 1.6;

export interface MonthNode {
  period: string; // "YYYY-MM"
  count: number;
  sources: Record<string, number>;
  topPeople: string[];
  color: string;
  x: number;
  z: number;
  height: number;
}

export interface DayNode {
  period: string; // "YYYY-MM-DD"
  count: number;
  sources: Record<string, number>;
  topPeople: string[];
  color: string;
  x: number;
  y: number;
  z: number;
  radius: number;
}

export interface SpiralLayout {
  months: MonthNode[];
  yearLabels: { year: number; x: number; z: number }[];
  /** Points of the spiral guide line. */
  spiralPath: [number, number, number][];
}

/** Position on the spiral `yearsSinceStart` turns out, `monthOffset` (0..12) months into the year. */
function spiralPoint(yearsSinceStart: number, monthOffset: number): { x: number; z: number } {
  const radius = INNER_RADIUS + (yearsSinceStart + monthOffset / 12) * YEAR_SPACING;
  const angle = (monthOffset / 12) * Math.PI * 2 - Math.PI / 2;
  return { x: radius * Math.cos(angle), z: radius * Math.sin(angle) };
}

export function layoutMonths(monthBuckets: TimelineBucket[]): SpiralLayout {
  const parsed = monthBuckets
    .map((bucket) => ({ bucket, month: parseMonth(bucket.period) }))
    .filter((entry): entry is { bucket: TimelineBucket; month: { year: number; month: number } } => entry.month !== null)
    .sort((a, b) => a.bucket.period.localeCompare(b.bucket.period));

  const first = parsed[0];
  const last = parsed.at(-1);
  if (!first || !last) return { months: [], yearLabels: [], spiralPath: [] };

  const firstYear = first.month.year;
  const lastYear = last.month.year;
  const busiestCount = Math.max(1, ...parsed.map((entry) => entry.bucket.count));

  const months: MonthNode[] = parsed.map(({ bucket, month }) => {
    const { x, z } = spiralPoint(month.year - firstYear, month.month - 1);
    return {
      period: bucket.period.slice(0, 7),
      count: bucket.count,
      sources: bucket.sources,
      topPeople: bucket.top_people,
      color: sourceMeta(dominantSource(bucket.sources)).color,
      x,
      z,
      height: MIN_COLUMN_HEIGHT + (bucket.count / busiestCount) * MAX_COLUMN_HEIGHT,
    };
  });

  // Year labels sit just before January of each year.
  const yearLabels: SpiralLayout["yearLabels"] = [];
  for (let year = firstYear; year <= lastYear; year++) {
    yearLabels.push({ year, ...spiralPoint(year - firstYear, -0.35) });
  }

  // Sample the spiral every quarter month so the guide line looks smooth.
  const spiralPath: SpiralLayout["spiralPath"] = [];
  const totalMonths = (lastYear - firstYear + 1) * 12;
  for (let monthsSinceStart = -0.5; monthsSinceStart <= totalMonths - 0.5; monthsSinceStart += 0.25) {
    const yearsSinceStart = Math.floor((monthsSinceStart + 0.5) / 12);
    const { x, z } = spiralPoint(yearsSinceStart, monthsSinceStart - yearsSinceStart * 12);
    spiralPath.push([x, 0.01, z]);
  }

  return { months, yearLabels, spiralPath };
}

/** Day spheres for `month`, placed on a ring above its column like the numbers on a clock face. */
export function layoutDays(month: MonthNode, dayBuckets: TimelineBucket[]): DayNode[] {
  const parsed = parseMonth(month.period);
  if (!parsed) return [];
  const numberOfDays = daysInMonth(parsed.year, parsed.month);
  const inMonth = dayBuckets.filter((bucket) => bucket.period.startsWith(month.period) && bucket.period.length >= 10);
  const busiestCount = Math.max(1, ...inMonth.map((bucket) => bucket.count));

  return inMonth.map((bucket) => {
    const dayOfMonth = Number(bucket.period.slice(8, 10));
    const angle = ((dayOfMonth - 1) / numberOfDays) * Math.PI * 2 - Math.PI / 2;
    return {
      period: bucket.period.slice(0, 10),
      count: bucket.count,
      sources: bucket.sources,
      topPeople: bucket.top_people,
      color: sourceMeta(dominantSource(bucket.sources)).color,
      x: month.x + DAY_RING_RADIUS * Math.cos(angle),
      y: month.height + 0.9,
      z: month.z + DAY_RING_RADIUS * Math.sin(angle),
      // sqrt: sphere size grows gently, so one very busy day doesn't dwarf the rest.
      radius: 0.1 + 0.22 * Math.sqrt(bucket.count / busiestCount),
    };
  });
}
