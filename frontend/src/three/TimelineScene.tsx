// The 3D Life explorer (React Three Fiber): months as columns on a spiral, the selected month's days
// as spheres above it. Positions come from spiralLayout.ts; the data comes from LifePage.
// This module (and everything three.js) is lazy-loaded by LifePage, so it never slows down other pages.
import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Html, Line, OrbitControls, Stars } from "@react-three/drei";
import * as THREE from "three";
import type { TimelineBucket } from "@/types/api";
import { formatPeriod } from "@/lib/periods";
import { CameraRig, type OrbitControlsHandle } from "./CameraRig";
import { DaySphere } from "./DaySphere";
import { MonthColumn } from "./MonthColumn";
import { SceneTooltip } from "./SceneTooltip";
import { DAY_RING_RADIUS, layoutDays, layoutMonths, type DayNode, type MonthNode } from "./spiralLayout";

const BACKGROUND_COLOR = "#0b0b14";
const ACCENT_COLOR = "#8b7cff";

interface TimelineSceneProps {
  months: TimelineBucket[];
  /** Day buckets of the selected month. */
  days: TimelineBucket[];
  selectedMonth: string | null;
  selectedDay: string | null;
  onSelectMonth: (month: string | null) => void;
  onSelectDay: (day: string) => void;
}

export default function TimelineScene({
  months,
  days,
  selectedMonth,
  selectedDay,
  onSelectMonth,
  onSelectDay,
}: TimelineSceneProps) {
  const controlsRef = useRef<OrbitControlsHandle>(null);
  const [hoveredMonth, setHoveredMonth] = useState<MonthNode | null>(null);
  const [hoveredDay, setHoveredDay] = useState<DayNode | null>(null);

  const layout = useMemo(() => layoutMonths(months), [months]);
  const selectedNode = layout.months.find((node) => node.period === selectedMonth) ?? null;
  const dayNodes = useMemo(() => (selectedNode ? layoutDays(selectedNode, days) : []), [selectedNode, days]);

  // How far the spiral reaches from the centre; sizes the floor, fog, stars and camera.
  const sceneRadius = useMemo(
    () => Math.max(8, ...layout.months.map((node) => Math.hypot(node.x, node.z))),
    [layout.months],
  );

  const cameraTarget = useMemo(
    () =>
      selectedNode
        ? new THREE.Vector3(selectedNode.x, selectedNode.height * 0.6, selectedNode.z)
        : new THREE.Vector3(0, 0.5, 0),
    [selectedNode],
  );

  // If the scene unmounts while hovering, don't leave the pointer cursor behind.
  useEffect(() => {
    return () => {
      document.body.style.cursor = "";
    };
  }, []);

  return (
    <Canvas
      camera={{ position: [0, sceneRadius * 1.1, sceneRadius * 1.6], fov: 50, near: 0.1, far: 1000 }}
      dpr={[1, 2]}
      // Clicking empty space clears the selection.
      onPointerMissed={() => onSelectMonth(null)}
      gl={{ antialias: true }}
    >
      <color attach="background" args={[BACKGROUND_COLOR]} />
      <fog attach="fog" args={[BACKGROUND_COLOR, sceneRadius * 2, sceneRadius * 5]} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 20, 10]} intensity={1.2} />
      <pointLight position={[0, 10, 0]} intensity={40} distance={60} color={ACCENT_COLOR} />
      <Stars radius={sceneRadius * 4} depth={40} count={2500} factor={3} fade speed={0.5} />

      {/* Floor disc and the spiral guide line */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
        <circleGeometry args={[sceneRadius + 3, 96]} />
        <meshStandardMaterial color="#12121f" roughness={1} />
      </mesh>
      {layout.spiralPath.length > 1 && (
        <Line points={layout.spiralPath} color="#4b4b7a" lineWidth={1.2} transparent opacity={0.8} />
      )}

      {layout.yearLabels.map((label) => (
        <Html key={label.year} position={[label.x * 1.04, 0.2, label.z * 1.04]} center zIndexRange={[10, 0]}>
          <div className="pointer-events-none select-none rounded bg-black/40 px-1.5 py-0.5 text-xs font-semibold text-white/80">
            {label.year}
          </div>
        </Html>
      ))}

      {layout.months.map((node) => (
        <MonthColumn
          key={node.period}
          node={node}
          selected={node.period === selectedMonth}
          dimmed={selectedMonth !== null && node.period !== selectedMonth}
          onHover={setHoveredMonth}
          onSelect={(clicked) => onSelectMonth(clicked.period === selectedMonth ? null : clicked.period)}
        />
      ))}

      {selectedNode && (
        // A faint ring marking the circle the day spheres sit on.
        <mesh position={[selectedNode.x, selectedNode.height + 0.9, selectedNode.z]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[DAY_RING_RADIUS - 0.05, DAY_RING_RADIUS + 0.02, 64]} />
          <meshBasicMaterial color={ACCENT_COLOR} transparent opacity={0.5} side={THREE.DoubleSide} />
        </mesh>
      )}
      {dayNodes.map((node) => (
        <DaySphere
          key={node.period}
          node={node}
          selected={node.period === selectedDay}
          onHover={setHoveredDay}
          onSelect={(clicked) => onSelectDay(clicked.period)}
        />
      ))}

      {hoveredMonth && !hoveredDay && (
        <Html position={[hoveredMonth.x, hoveredMonth.height + 0.3, hoveredMonth.z]} center zIndexRange={[100, 50]}>
          <SceneTooltip
            title={formatPeriod(hoveredMonth.period)}
            count={hoveredMonth.count}
            sources={hoveredMonth.sources}
            people={hoveredMonth.topPeople}
          />
        </Html>
      )}
      {hoveredDay && (
        <Html position={[hoveredDay.x, hoveredDay.y + hoveredDay.radius + 0.2, hoveredDay.z]} center zIndexRange={[100, 50]}>
          <SceneTooltip
            title={formatPeriod(hoveredDay.period)}
            count={hoveredDay.count}
            sources={hoveredDay.sources}
            people={hoveredDay.topPeople}
          />
        </Html>
      )}

      {/* Drag to orbit, scroll to zoom; the camera can't go below the floor. */}
      <OrbitControls
        ref={controlsRef}
        enableDamping
        dampingFactor={0.08}
        minDistance={3}
        maxDistance={sceneRadius * 4}
        maxPolarAngle={Math.PI / 2.05}
      />
      <CameraRig
        controlsRef={controlsRef}
        target={cameraTarget}
        fitDistance={Math.hypot(sceneRadius * 1.1, sceneRadius * 1.6)}
      />
    </Canvas>
  );
}
