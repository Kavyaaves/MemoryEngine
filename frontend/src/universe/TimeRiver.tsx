// The time river: a faint line along the x axis (time) with specks of light drifting slowly
// towards the present. Purely decorative — it gives the eye a direction, "the past is to the left".
import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";
import { glowTexture } from "./glowTexture";

const PARTICLES_PER_CELL = 6;
const CELL_LENGTH = 6; // the particle pattern repeats every CELL_LENGTH units, so shifting by one cell is seamless
const DRIFT_UNITS_PER_SECOND = 1.2;
const RIVER_COLOR = "#7dd3fc";

interface TimeRiverProps {
  fromX: number;
  toX: number;
}

export function TimeRiver({ fromX, toX }: TimeRiverProps) {
  const drifting = useRef<THREE.Points>(null);

  const geometry = useMemo(() => {
    // The same small random pattern in every cell (seeded, so it looks alike on every visit).
    let seed = 7;
    const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const pattern = Array.from({ length: PARTICLES_PER_CELL }, () => ({
      dx: random() * CELL_LENGTH,
      angle: random() * Math.PI * 2,
      radius: 0.2 + random() * 1.4,
    }));
    const cells = Math.ceil((toX - fromX) / CELL_LENGTH) + 1;
    const positions = new Float32Array(cells * PARTICLES_PER_CELL * 3);
    let i = 0;
    for (let cell = 0; cell < cells; cell++) {
      for (const p of pattern) {
        positions[i++] = fromX + cell * CELL_LENGTH + p.dx;
        positions[i++] = Math.sin(p.angle) * p.radius;
        positions[i++] = Math.cos(p.angle) * p.radius;
      }
    }
    const buffer = new THREE.BufferGeometry();
    buffer.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return buffer;
  }, [fromX, toX]);

  useFrame(({ clock }) => {
    if (drifting.current) drifting.current.position.x = (clock.elapsedTime * DRIFT_UNITS_PER_SECOND) % CELL_LENGTH;
  });

  return (
    <group>
      <Line points={[[fromX, 0, 0], [toX, 0, 0]]} color={RIVER_COLOR} lineWidth={1.4} transparent opacity={0.45} />
      <points ref={drifting} geometry={geometry}>
        <pointsMaterial
          size={0.55}
          map={glowTexture()}
          color={RIVER_COLOR}
          transparent
          opacity={0.7}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  );
}
