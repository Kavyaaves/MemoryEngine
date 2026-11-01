// Years and months along the time river.
//  - a year is a large faint ring around the river at 1 January, with its number above it;
//  - months are small rings, shown only once you are close enough (progressive disclosure),
//    and only their names near the camera get a label.
// Clicking a year label glides to that year.
import { useMemo } from "react";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { glowTexture } from "./glowTexture";
import type { UniverseLayout, UniversePeriod } from "@/types/api";
import type { ZoomLevel } from "@/stores/universeStore";
import { dateX, MONTH_NAMES } from "./universeMath";

const YEAR_RING_RADIUS = 24;
const MONTH_RING_RADIUS = 13;
const MONTH_LABEL_RANGE = 160; // units from the camera target within which month names are shown

interface YearGatesProps {
  years: UniversePeriod[];
  months: UniversePeriod[];
  layout: UniverseLayout;
  zoom: ZoomLevel;
  cameraX: number;
  onSelectYear: (year: string) => void;
}

/** Two faint glowing clouds per year (a colour that shifts from year to year) — depth, nothing more. */
function nebulaGeometry(years: UniversePeriod[], layout: UniverseLayout): THREE.BufferGeometry {
  const positions: number[] = [];
  const colors: number[] = [];
  const color = new THREE.Color();
  years.forEach((year, index) => {
    const x = dateX(`${year.period}-07-01`, layout);
    color.setHSL((0.62 + index * 0.07) % 1, 0.6, 0.55);
    positions.push(x - 30, 8, -18, x + 25, -6, 14);
    colors.push(color.r, color.g, color.b, color.r * 0.8, color.g * 0.8, color.b);
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  return geometry;
}

export function YearGates({ years, months, layout, zoom, cameraX, onSelectYear }: YearGatesProps) {
  const showMonths = zoom !== "universe";
  const nebula = useMemo(() => nebulaGeometry(years, layout), [years, layout]);
  return (
    <group>
      <points geometry={nebula} raycast={() => null}>
        <pointsMaterial size={110} map={glowTexture()} vertexColors transparent opacity={0.1} depthWrite={false}
                        blending={THREE.AdditiveBlending} />
      </points>
      {years.map((year) => {
        const x = dateX(`${year.period}-01-01`, layout);
        return (
          <group key={year.period} position={[x, 0, 0]}>
            <mesh rotation={[0, Math.PI / 2, 0]}>
              <torusGeometry args={[YEAR_RING_RADIUS, 0.05, 8, 128]} />
              <meshBasicMaterial color="#a5b4fc" transparent opacity={0.28} depthWrite={false} />
            </mesh>
            <Html position={[0, YEAR_RING_RADIUS + 3, 0]} center zIndexRange={[20, 10]}>
              <button
                type="button"
                onClick={() => onSelectYear(year.period)}
                className="cursor-pointer select-none whitespace-nowrap font-light tracking-[0.3em] text-indigo-100/80 transition-colors hover:text-white"
                style={{ fontSize: zoom === "universe" ? 28 : 18 }}
                title={`${year.memory_count.toLocaleString()} memories · ${year.book_count} books`}
              >
                {year.period}
              </button>
            </Html>
          </group>
        );
      })}

      {showMonths &&
        months.map((month) => {
          const x = dateX(`${month.period}-01`, layout);
          const labelled = Math.abs(x - cameraX) < MONTH_LABEL_RANGE && zoom !== "year";
          return (
            <group key={month.period} position={[x, 0, 0]}>
              <mesh rotation={[0, Math.PI / 2, 0]}>
                <ringGeometry args={[MONTH_RING_RADIUS - 0.04, MONTH_RING_RADIUS, 96]} />
                <meshBasicMaterial color="#c7d2fe" transparent opacity={0.1} side={THREE.DoubleSide} depthWrite={false} />
              </mesh>
              {labelled && (
                <Html position={[0, MONTH_RING_RADIUS + 1.2, 0]} center zIndexRange={[15, 5]}>
                  <span className="pointer-events-none select-none whitespace-nowrap text-[11px] uppercase tracking-[0.25em] text-indigo-100/50">
                    {MONTH_NAMES[Number(month.period.slice(5, 7)) - 1]}
                  </span>
                </Html>
              )}
            </group>
          );
        })}
    </group>
  );
}
