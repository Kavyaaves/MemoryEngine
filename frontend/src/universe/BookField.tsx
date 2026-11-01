// Every Memory Book as a small glowing book floating around the time river.
//
// One InstancedMesh draws all books in a single draw call (a universe can hold a thousand books).
// Each book's place comes from the server and never changes; this component only decides how it
// looks right now:
//   - size grows gently with the number of memories;
//   - the cover faces away from the river, so you see covers when you look at a year from the side;
//   - hovered and open books are slightly larger;
//   - a book that just appeared grows out of nothing, and a book that just gained memories pulses
//     twice ("New memories discovered") — nothing else moves.
import { useLayoutEffect, useMemo, useRef } from "react";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { Book } from "@/types/api";
import { useUniverseStore, type FreshMark } from "@/stores/universeStore";
import { glowTexture } from "./glowTexture";
import { bookScale, eventColor } from "./universeMath";

const APPEAR_MS = 1800;
const PULSE_MS = 1400;
const HOVER_SCALE = 1.18;

const temp = new THREE.Object3D();
const color = new THREE.Color();

/** A small fixed tilt per book (from its id), so the field looks organic rather than gridded. */
function tiltOf(id: string): number {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) | 0;
  return ((hash % 1000) / 1000) * 0.35;
}

/** Extra scale from the appear/grow animation (1 = at rest). */
function animationScale(mark: FreshMark | undefined, now: number): { scale: number; active: boolean } {
  if (!mark) return { scale: 1, active: false };
  const elapsed = now - mark.at;
  if (mark.kind === "new") {
    if (elapsed >= APPEAR_MS) return { scale: 1, active: false };
    const t = elapsed / APPEAR_MS;
    const back = 1.6; // "ease out back": overshoots a little, then settles
    return { scale: Math.max(0.001, 1 + (back + 1) * (t - 1) ** 3 + back * (t - 1) ** 2), active: true };
  }
  if (elapsed >= PULSE_MS * 2) return { scale: 1, active: false };
  return { scale: 1 + 0.22 * Math.sin((elapsed / PULSE_MS) * Math.PI) ** 2, active: true };
}

interface BookFieldProps {
  books: Book[];
  openBookId: string | null;
  onSelect: (book: Book) => void;
}

export function BookField({ books, openBookId, onSelect }: BookFieldProps) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const hoveredBookId = useUniverseStore((state) => state.hoveredBookId);
  const setHoveredBook = useUniverseStore((state) => state.setHoveredBook);
  const needsLayout = useRef(true);

  const glow = useMemo(() => {
    const positions = new Float32Array(books.length * 3);
    const colors = new Float32Array(books.length * 3);
    books.forEach((book, i) => {
      positions.set(book.position, i * 3);
      color.set(eventColor(book.event_type));
      colors.set([color.r, color.g, color.b], i * 3);
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return geometry;
  }, [books]);

  // Colours change only when the books do.
  useLayoutEffect(() => {
    const instances = mesh.current;
    if (!instances) return;
    books.forEach((book, i) => instances.setColorAt(i, color.set(eventColor(book.event_type))));
    if (instances.instanceColor) instances.instanceColor.needsUpdate = true;
    needsLayout.current = true;
  }, [books]);

  useLayoutEffect(() => {
    needsLayout.current = true;
  }, [hoveredBookId, openBookId]);

  useFrame(() => {
    const instances = mesh.current;
    if (!instances) return;
    const now = Date.now();
    const fresh = useUniverseStore.getState().freshBooks;
    let animating = false;
    if (!needsLayout.current && !books.some((book) => animationScale(fresh[book.id], now).active)) return;

    books.forEach((book, i) => {
      const [x, y, z] = book.position;
      const { scale: animated, active } = animationScale(fresh[book.id], now);
      animating ||= active;
      const emphasis = book.id === hoveredBookId ? HOVER_SCALE : 1;
      // The open book is drawn by OpenBook instead; shrink this one to nothing.
      const scale = book.id === openBookId ? 0.0001 : bookScale(book.memory_count) * emphasis * animated;
      temp.position.set(x, y, z);
      // Face outward from the river: rotate around x by the book's angle around the river.
      temp.rotation.set(-Math.atan2(y, z), tiltOf(book.id), 0);
      temp.scale.setScalar(scale);
      temp.updateMatrix();
      instances.setMatrixAt(i, temp.matrix);
    });
    instances.instanceMatrix.needsUpdate = true;
    instances.computeBoundingSphere(); // keeps clicks working on books far from the origin
    needsLayout.current = animating;
  });

  const bookAt = (event: ThreeEvent<PointerEvent | MouseEvent>) =>
    event.instanceId !== undefined ? books[event.instanceId] : undefined;

  return (
    <group>
      <instancedMesh
        key={books.length} // a different count needs a new InstancedMesh
        ref={mesh}
        args={[undefined, undefined, books.length]}
        onPointerMove={(event) => {
          event.stopPropagation();
          const book = bookAt(event);
          setHoveredBook(book?.id ?? null);
          document.body.style.cursor = book ? "pointer" : "";
        }}
        onPointerOut={() => {
          setHoveredBook(null);
          document.body.style.cursor = "";
        }}
        onClick={(event) => {
          event.stopPropagation();
          const book = bookAt(event);
          if (book) onSelect(book);
        }}
      >
        <boxGeometry args={[0.9, 1.25, 0.26]} />
        <meshStandardMaterial roughness={0.45} metalness={0.15} emissive="#20204a" emissiveIntensity={0.9} />
      </instancedMesh>
      <points geometry={glow} raycast={() => null}>
        <pointsMaterial
          size={4.5}
          map={glowTexture()}
          vertexColors
          transparent
          opacity={0.38}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  );
}
