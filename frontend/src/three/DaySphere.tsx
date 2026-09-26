import { useMemo, useState } from "react";
import type { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { DayNode } from "./spiralLayout";

interface DaySphereProps {
  node: DayNode;
  selected: boolean;
  onHover: (node: DayNode | null) => void;
  onSelect: (node: DayNode) => void;
}

/** One day of the selected month, floating above its column; bigger = more memories. */
export function DaySphere({ node, selected, onHover, onSelect }: DaySphereProps) {
  const [hovered, setHovered] = useState(false);
  const color = useMemo(() => new THREE.Color(node.color), [node.color]);

  return (
    <mesh
      position={[node.x, node.y, node.z]}
      scale={hovered || selected ? 1.35 : 1}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => {
        event.stopPropagation();
        setHovered(true);
        onHover(node);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHovered(false);
        onHover(null);
        document.body.style.cursor = "";
      }}
      onClick={(event: ThreeEvent<MouseEvent>) => {
        event.stopPropagation();
        onSelect(node);
      }}
    >
      <sphereGeometry args={[node.radius, 20, 20]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={selected ? 1 : 0.45} />
    </mesh>
  );
}
