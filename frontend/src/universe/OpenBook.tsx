// The open Memory Book: drawn in detail where the small book was, its cover swinging open, and its
// pages fanned out in an arc facing you (oldest on the left). Clicking a page opens it in the reader.
// Books with many pages show a window of MAX_VISIBLE_PAGES around the open page; the reader lists all.
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { Sparkles } from "lucide-react";
import type { Book, MemoryPage } from "@/types/api";
import { useUniverseStore } from "@/stores/universeStore";
import { bookCameraPosition, ease, eventColor } from "./universeMath";

const OPEN_MS = 900;
const COVER_OPEN_ANGLE = -2.2; // radians the front cover swings
const MAX_VISIBLE_PAGES = 14;
const ARC_RADIUS = 2.3;

interface OpenBookProps {
  book: Book;
  pages: MemoryPage[];
  openPageId: string | null;
  onOpenPage: (pageId: string) => void;
}

/** A right/up basis facing the camera's resting place, so the page arc is always readable. */
function viewBasis(viewer: THREE.Vector3, position: THREE.Vector3) {
  const forward = position.clone().sub(viewer).normalize();
  let right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0));
  if (right.lengthSq() < 1e-6) right = new THREE.Vector3(1, 0, 0);
  right.normalize();
  const up = new THREE.Vector3().crossVectors(right, forward).normalize();
  return { right, up };
}

function visibleWindow(pages: MemoryPage[], openPageId: string | null): MemoryPage[] {
  if (pages.length <= MAX_VISIBLE_PAGES) return pages;
  const openIndex = pages.findIndex((page) => page.id === openPageId);
  const center = openIndex >= 0 ? openIndex : pages.length - 1; // default: the most recent pages
  const start = Math.max(0, Math.min(pages.length - MAX_VISIBLE_PAGES, center - Math.floor(MAX_VISIBLE_PAGES / 2)));
  return pages.slice(start, start + MAX_VISIBLE_PAGES);
}

export function OpenBook({ book, pages, openPageId, onOpenPage }: OpenBookProps) {
  const group = useRef<THREE.Group>(null);
  const cover = useRef<THREE.Group>(null);
  const openedAt = useRef(0);
  const [hoveredPageId, setHoveredPageId] = useState<string | null>(null);
  const freshPages = useUniverseStore((state) => state.freshPages);

  const position = useMemo(() => new THREE.Vector3(...book.position), [book.position]);
  const viewer = useMemo(() => new THREE.Vector3(...bookCameraPosition(book.position)), [book.position]);
  const { right, up } = useMemo(() => viewBasis(viewer, position), [viewer, position]);
  const shown = visibleWindow(pages, openPageId);
  const tint = eventColor(book.event_type);

  useLayoutEffect(() => {
    openedAt.current = performance.now();
    group.current?.lookAt(viewer);
  }, [book.id, viewer]);

  useFrame(() => {
    if (cover.current) {
      const t = ease((performance.now() - openedAt.current) / OPEN_MS);
      cover.current.rotation.y = COVER_OPEN_ANGLE * t;
    }
  });

  return (
    <group>
      {/* The book itself, facing the viewer; the front cover hinges on its left edge. */}
      <group ref={group} position={position} scale={1.35}>
        <mesh position={[0, 0, -0.1]}>
          <boxGeometry args={[0.9, 1.25, 0.04]} />
          <meshStandardMaterial color={tint} emissive={tint} emissiveIntensity={0.25} />
        </mesh>
        <mesh>
          <boxGeometry args={[0.84, 1.19, 0.16]} />
          <meshStandardMaterial color="#f1f5f9" emissive="#e2e8f0" emissiveIntensity={0.3} />
        </mesh>
        <group ref={cover} position={[-0.45, 0, 0.1]}>
          <mesh position={[0.45, 0, 0]}>
            <boxGeometry args={[0.9, 1.25, 0.04]} />
            <meshStandardMaterial color={tint} emissive={tint} emissiveIntensity={0.35} />
          </mesh>
        </group>
      </group>

      {shown.map((page, index) => {
        // From 160° (left, oldest) to 20° (right, newest), in the plane facing the viewer.
        const angle = THREE.MathUtils.degToRad(shown.length === 1 ? 90 : 160 - (140 * index) / (shown.length - 1));
        const spot = position.clone()
          .add(right.clone().multiplyScalar(Math.cos(angle) * ARC_RADIUS))
          .add(up.clone().multiplyScalar(Math.sin(angle) * ARC_RADIUS * 0.75 + 0.5));
        const isOpen = page.id === openPageId;
        const isHovered = page.id === hoveredPageId;
        const isFresh = Boolean(freshPages[page.id]);
        return (
          <PageCard
            key={page.id}
            position={spot}
            viewer={viewer}
            page={page}
            highlighted={isOpen || isHovered}
            open={isOpen}
            fresh={isFresh}
            onHover={(hovering) => setHoveredPageId(hovering ? page.id : null)}
            onClick={() => onOpenPage(page.id)}
          />
        );
      })}

      <Html position={[position.x, position.y - 1.4, position.z]} center zIndexRange={[40, 30]}>
        <div className="pointer-events-none max-w-64 select-none text-center text-xs text-white/80 drop-shadow">
          {book.title}
          {pages.length > shown.length && (
            <div className="text-[10px] text-white/50">{shown.length} of {pages.length} pages shown</div>
          )}
        </div>
      </Html>
    </group>
  );
}

interface PageCardProps {
  position: THREE.Vector3;
  viewer: THREE.Vector3;
  page: MemoryPage;
  highlighted: boolean;
  open: boolean;
  fresh: boolean;
  onHover: (hovering: boolean) => void;
  onClick: () => void;
}

function PageCard({ position, viewer, page, highlighted, open, fresh, onHover, onClick }: PageCardProps) {
  const mesh = useRef<THREE.Mesh>(null);
  useLayoutEffect(() => {
    mesh.current?.lookAt(viewer);
  }, [viewer]);
  const day = new Date(`${page.day}T00:00:00`);
  return (
    <group position={position}>
      <mesh
        ref={mesh}
        scale={highlighted ? 1.12 : 1}
        onPointerOver={(event) => {
          event.stopPropagation();
          onHover(true);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          onHover(false);
          document.body.style.cursor = "";
        }}
        onClick={(event) => {
          event.stopPropagation();
          onClick();
        }}
      >
        <planeGeometry args={[0.6, 0.8]} />
        <meshBasicMaterial
          color={open ? "#fde68a" : fresh ? "#fef3c7" : "#e2e8f0"}
          transparent
          opacity={highlighted ? 0.95 : 0.7}
          side={THREE.DoubleSide}
        />
      </mesh>
      <Html position={[0, -0.72, 0]} center zIndexRange={[35, 25]}>
        <div className="pointer-events-none select-none whitespace-nowrap text-center text-[10px] leading-tight text-white/75">
          {fresh && <Sparkles className="mr-0.5 inline size-2.5 text-amber-200" />}
          {day.toLocaleDateString(undefined, { day: "numeric", month: "short" })}
          <div className="text-white/45">{page.memory_count}</div>
        </div>
      </Html>
    </group>
  );
}
