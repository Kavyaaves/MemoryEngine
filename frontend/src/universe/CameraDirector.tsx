// Moves the camera. Three jobs:
//  1. Flights: when the store's `flight` changes, glide through its waypoints one after another
//     (both the camera and the point it orbits), with a smooth start and stop. Grabbing the scene
//     with the mouse cancels the flight — the user is always in control.
//  2. Reporting: a few times a second, tell the store the zoom level (progressive disclosure) and
//     where along the time river the camera is (breadcrumb, time scrubber).
//  3. Memory: the camera's place is saved in this browser, so reopening the page — or new memories
//     arriving — never throws you back to the start. (Data updates never touch the camera at all.)
import { useEffect, useRef, type RefObject } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { useUniverseStore, type Vec3, type Waypoint } from "@/stores/universeStore";
import { ease, zoomFor } from "./universeMath";
import type { OrbitControlsHandle } from "./controls";

const STORAGE_KEY = "memory-universe-camera";
const REPORT_EVERY_MS = 250;
const SAVE_EVERY_MS = 2000;
const KEY_GLIDE_UNITS = 12; // ← / → glide along time

interface CameraDirectorProps {
  controlsRef: RefObject<OrbitControlsHandle | null>;
  /** Where to start when nothing was saved (the latest year, seen from the side). */
  initial: Waypoint;
}

interface Segment {
  waypoint: Waypoint;
  fromPosition: THREE.Vector3;
  fromTarget: THREE.Vector3;
  toPosition: THREE.Vector3;
  toTarget: THREE.Vector3;
  startedAt: number;
}

function loadSaved(): { position: Vec3; target: Vec3 } | null {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    return saved?.position?.length === 3 && saved?.target?.length === 3 ? saved : null;
  } catch {
    return null; // private mode or corrupt value: just start at the default view
  }
}

function endPosition(waypoint: Waypoint, camera: THREE.Camera, currentTarget: THREE.Vector3): THREE.Vector3 {
  const target = new THREE.Vector3(...waypoint.target);
  const direction = waypoint.direction
    ? new THREE.Vector3(...waypoint.direction)
    : camera.position.clone().sub(currentTarget).normalize();
  return target.add(direction.multiplyScalar(waypoint.distance));
}

export function CameraDirector({ controlsRef, initial }: CameraDirectorProps) {
  const camera = useThree((state) => state.camera);
  const flight = useUniverseStore((state) => state.flight);
  const queue = useRef<Waypoint[]>([]);
  const segment = useRef<Segment | null>(null);
  const lastReport = useRef(0);
  const lastSave = useRef(0);
  const placed = useRef(false);

  // First frame: restore the saved view, or the initial one.
  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls || placed.current) return;
    placed.current = true;
    const saved = loadSaved();
    if (saved) {
      camera.position.set(...saved.position);
      controls.target.set(...saved.target);
    } else {
      controls.target.set(...initial.target);
      camera.position.copy(endPosition(initial, camera, controls.target));
    }
    controls.update();
  }, [camera, controlsRef, initial]);

  // A new flight replaces whatever was flying.
  useEffect(() => {
    if (!flight) return;
    queue.current = [...flight.waypoints];
    segment.current = null;
  }, [flight]);

  // The user grabbing the scene cancels a flight.
  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls) return;
    const cancel = () => {
      queue.current = [];
      segment.current = null;
      useUniverseStore.getState().setFlightLabel(null);
    };
    controls.addEventListener("start", cancel);
    return () => controls.removeEventListener("start", cancel);
  }, [controlsRef]);

  // ← / → glide along time (ignored while typing in an input).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = event.target instanceof HTMLElement && event.target.closest("input, textarea, [contenteditable]");
      const controls = controlsRef.current;
      if (typing || !controls || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
      const step = event.key === "ArrowRight" ? KEY_GLIDE_UNITS : -KEY_GLIDE_UNITS;
      const target = controls.target;
      const distance = camera.position.distanceTo(target);
      useUniverseStore.getState().fly([{ target: [target.x + step, target.y, target.z], distance, durationMs: 450 }]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [camera, controlsRef]);

  useFrame(() => {
    const controls = controlsRef.current;
    if (!controls) return;
    const now = performance.now();

    if (!segment.current && queue.current.length > 0) {
      const waypoint = queue.current.shift()!;
      segment.current = {
        waypoint,
        fromPosition: camera.position.clone(),
        fromTarget: controls.target.clone(),
        toPosition: endPosition(waypoint, camera, controls.target),
        toTarget: new THREE.Vector3(...waypoint.target),
        startedAt: now,
      };
      useUniverseStore.getState().setFlightLabel(waypoint.label ?? null);
    }

    const current = segment.current;
    if (current) {
      const t = ease((now - current.startedAt) / current.waypoint.durationMs);
      camera.position.lerpVectors(current.fromPosition, current.toPosition, t);
      controls.target.lerpVectors(current.fromTarget, current.toTarget, t);
      controls.update();
      if (t >= 1) {
        segment.current = null;
        current.waypoint.onArrive?.();
        if (queue.current.length === 0) useUniverseStore.getState().setFlightLabel(null);
      }
    }

    if (now - lastReport.current > REPORT_EVERY_MS) {
      lastReport.current = now;
      const store = useUniverseStore.getState();
      store.setZoom(zoomFor(camera.position.distanceTo(controls.target)));
      if (Math.abs(store.cameraX - controls.target.x) > 1) store.setCameraX(controls.target.x);
    }
    if (now - lastSave.current > SAVE_EVERY_MS) {
      lastSave.current = now;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
          position: camera.position.toArray(),
          target: controls.target.toArray(),
        }));
      } catch {
        // storage unavailable: the view just isn't remembered
      }
    }
  });

  return null;
}
