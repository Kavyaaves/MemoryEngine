// The Memory Universe in 3D (React Three Fiber). Lazy-loaded by the Memories page, like the Life scene.
//
//   time river (x = time) ── year gates ── month rings ── Memory Books floating around the river
//   open book → its pages fan out → the reader panel (HTML, outside this canvas) shows the memories
//
// What you see depends on how close you are (progressive disclosure): far away only years and
// specks of light; closer, month names; closer still, book titles; an open book shows its pages.
// Data never moves the camera: new books fade in where the server placed them.
import { useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import type * as THREE from "three";
import type { Book, BookDetail, Universe } from "@/types/api";
import { useUniverseStore, type Waypoint } from "@/stores/universeStore";
import { BookField } from "./BookField";
import { BookLabels } from "./BookLabels";
import { CameraDirector } from "./CameraDirector";
import { ConnectionArcs } from "./ConnectionArcs";
import type { OrbitControlsHandle } from "./controls";
import { OpenBook } from "./OpenBook";
import { TimeRiver } from "./TimeRiver";
import { dateX, OVERVIEW_DIRECTION, YEAR_VIEW_DISTANCE } from "./universeMath";
import { YearGates } from "./YearGates";

const SPACE_COLOR = "#04050d";
const RIVER_MARGIN = 120; // how far the river runs past the first and last memory

interface UniverseSceneProps {
  universe: Universe;
  openBookDetail: BookDetail | undefined;
  onSelectBook: (book: Book) => void;
  onOpenPage: (pageId: string) => void;
  onSelectYear: (year: string) => void;
}

/** Stars that travel with the camera: the river is thousands of units long, the sky should feel infinite. */
function FollowingStars() {
  const group = useRef<THREE.Group>(null);
  const camera = useThree((state) => state.camera);
  useFrame(() => group.current?.position.copy(camera.position));
  return (
    <group ref={group}>
      <Stars radius={600} depth={250} count={5000} factor={7} saturation={0.2} fade speed={0.25} />
    </group>
  );
}

export default function UniverseScene({ universe, openBookDetail, onSelectBook, onOpenPage, onSelectYear }: UniverseSceneProps) {
  const controlsRef = useRef<OrbitControlsHandle>(null);
  const openBookId = useUniverseStore((state) => state.openBookId);
  const openPageId = useUniverseStore((state) => state.openPageId);
  const zoom = useUniverseStore((state) => state.zoom);
  const cameraX = useUniverseStore((state) => state.cameraX);

  const { layout, books, years, months } = universe;
  const openBook = books.find((book) => book.id === openBookId) ?? null;

  const [fromX, toX] = useMemo(() => {
    const xs = books.map((book) => book.position[0]);
    if (years.length) xs.push(dateX(`${years[0].period}-01-01`, layout), dateX(`${years.at(-1)!.period}-12-31`, layout));
    return xs.length ? [Math.min(...xs) - RIVER_MARGIN, Math.max(...xs) + RIVER_MARGIN] : [-RIVER_MARGIN, RIVER_MARGIN];
  }, [books, years, layout]);

  // First visit: the most recent year, seen from the side.
  const initial = useMemo<Waypoint>(() => {
    const lastYear = years.at(-1)?.period;
    const x = lastYear ? dateX(`${lastYear}-07-01`, layout) : (fromX + toX) / 2;
    return { target: [x, 0, 0], distance: YEAR_VIEW_DISTANCE, direction: OVERVIEW_DIRECTION, durationMs: 0 };
  }, [years, layout, fromX, toX]);

  // Don't leave a pointer cursor behind if the scene unmounts mid-hover.
  useEffect(() => () => {
    document.body.style.cursor = "";
  }, []);

  return (
    <Canvas camera={{ fov: 50, near: 0.1, far: 4000 }} dpr={[1, 2]} gl={{ antialias: true }}>
      <color attach="background" args={[SPACE_COLOR]} />
      <fog attach="fog" args={[SPACE_COLOR, 260, 1100]} />
      <ambientLight intensity={0.45} />
      <hemisphereLight args={["#9fb4ff", "#1c1033", 0.6]} />
      <directionalLight position={[40, 80, 60]} intensity={0.9} />
      <FollowingStars />

      <TimeRiver fromX={fromX} toX={toX} />
      <YearGates years={years} months={months} layout={layout} zoom={zoom} cameraX={cameraX} onSelectYear={onSelectYear} />
      <BookField books={books} openBookId={openBookId} onSelect={onSelectBook} />
      <BookLabels books={books} zoom={zoom} openBookId={openBookId} controlsRef={controlsRef} />

      {openBook && (
        <OpenBook
          book={openBook}
          pages={openBookDetail?.book.id === openBook.id ? openBookDetail.pages : []}
          openPageId={openPageId}
          onOpenPage={onOpenPage}
        />
      )}
      {openBook && openBookDetail?.book.id === openBook.id && (
        <ConnectionArcs from={openBook} related={openBookDetail.related} onVisit={onSelectBook} />
      )}

      {/* Drag to orbit, right-drag to slide along time, scroll to zoom. */}
      <OrbitControls
        ref={controlsRef}
        enableDamping
        dampingFactor={0.07}
        minDistance={3}
        maxDistance={900}
        screenSpacePanning
        // The scene spans a whole year down to one page, so each wheel notch zooms by about 15%.
        zoomSpeed={2.5}
      />
      <CameraDirector controlsRef={controlsRef} initial={initial} />
    </Canvas>
  );
}
