import { useEffect, useRef, type ComponentRef, type RefObject } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import type { OrbitControls } from "@react-three/drei";
import * as THREE from "three";

export type OrbitControlsHandle = ComponentRef<typeof OrbitControls>;

interface CameraRigProps {
  controlsRef: RefObject<OrbitControlsHandle | null>;
  /** The point the camera should look at (the selected month, or the centre). */
  target: THREE.Vector3;
  /** Camera distance that fits the whole spiral on a wide screen. */
  fitDistance: number;
}

/**
 * Keeps the camera framed:
 *  - once the canvas size is known, pulls the camera back on narrow/portrait screens so the spiral fits;
 *  - whenever `target` changes, glides the orbit centre there over a few frames instead of jumping.
 */
export function CameraRig({ controlsRef, target, fitDistance }: CameraRigProps) {
  const camera = useThree((state) => state.camera);
  const size = useThree((state) => state.size);
  const fitted = useRef(false);
  const gliding = useRef(true);

  useEffect(() => {
    if (fitted.current || size.width === 0 || size.height === 0) return;
    fitted.current = true;
    const aspectRatio = size.width / size.height;
    camera.position.setLength(fitDistance / Math.min(1, aspectRatio * 1.15));
    camera.updateProjectionMatrix();
  }, [camera, size, fitDistance]);

  useEffect(() => {
    gliding.current = true;
  }, [target]);

  // useFrame runs on every rendered frame (~60 times a second).
  useFrame(() => {
    const controls = controlsRef.current;
    if (!controls || !gliding.current) return;
    controls.target.lerp(target, 0.08); // move 8% of the remaining distance each frame
    controls.update();
    if (controls.target.distanceTo(target) < 0.01) gliding.current = false;
  });

  return null;
}
