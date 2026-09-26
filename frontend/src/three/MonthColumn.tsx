import { useMemo, useState } from "react";
import type { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { MonthNode } from "./spiralLayout";

interface MonthColumnProps {
  node: MonthNode;
  selected: boolean;
  /** Faded out because another month is selected. */
  dimmed: boolean;
  onHover: (node: MonthNode | null) => void;
  onSelect: (node: MonthNode) => void;
}

/** One month as a glowing box standing on the spiral; taller = more memories. */
export function MonthColumn({ node, selected, dimmed, onHover, onSelect }: MonthColumnProps) {
  const [hovered, setHovered] = useState(false);
  const color = useMemo(() => new THREE.Color(node.color), [node.color]);
  const highlighted = hovered || selected;

  return (
    <mesh
      // A box is centred on its position, so lift it by half its height to stand on the floor.
      position={[node.x, node.height / 2, node.z]}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => {
        event.stopPropagation(); // only the front-most object under the pointer reacts
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
      <boxGeometry args={[0.55, node.height, 0.55]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={highlighted ? 0.7 : 0.15}
        transparent
        opacity={dimmed ? 0.35 : 0.95}
        roughness={0.4}
        metalness={0.1}
      />
    </mesh>
  );
}
