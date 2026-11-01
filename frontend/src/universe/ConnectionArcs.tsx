// Soft arcs from the open book to its related books (backend graph edges):
//   pink = a person who is in both books · teal = the two books' memories are similar.
// Clicking the arc's end label glides to that book.
import { Html, QuadraticBezierLine } from "@react-three/drei";
import type { Book, RelatedBook } from "@/types/api";
import type { Vec3 } from "@/stores/universeStore";

const REASON_COLOR: Record<RelatedBook["reason"], string> = {
  same_person: "#f9a8d4",
  similar_memories: "#5eead4",
};

interface ConnectionArcsProps {
  from: Book;
  related: RelatedBook[];
  onVisit: (book: Book) => void;
}

/** The arc bulges away from the river so it doesn't cut through the books in between. */
function arcMiddle(a: Vec3, b: Vec3): Vec3 {
  const middle: Vec3 = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
  const radius = Math.hypot(middle[1], middle[2]) || 1;
  const lift = Math.min(40, Math.abs(a[0] - b[0]) * 0.18 + 4);
  return [middle[0], middle[1] + (middle[1] / radius) * lift + lift * 0.4, middle[2] + (middle[2] / radius) * lift];
}

export function ConnectionArcs({ from, related, onVisit }: ConnectionArcsProps) {
  return (
    <group>
      {related.map(({ book, reason, label }) => (
        <group key={book.id}>
          <QuadraticBezierLine
            start={from.position}
            end={book.position}
            mid={arcMiddle(from.position, book.position)}
            color={REASON_COLOR[reason]}
            lineWidth={1.2}
            transparent
            opacity={0.55}
            dashed
            dashSize={0.8}
            gapSize={0.5}
          />
          <Html position={[book.position[0], book.position[1] + 1.4, book.position[2]]} center zIndexRange={[45, 35]}>
            <button
              type="button"
              onClick={() => onVisit(book)}
              className="max-w-44 cursor-pointer truncate rounded-full border border-white/15 bg-slate-950/70 px-2 py-0.5 text-[10px] text-white/80 backdrop-blur transition-colors hover:bg-slate-900 hover:text-white"
              title={label}
            >
              {book.title}
            </button>
          </Html>
        </group>
      ))}
    </group>
  );
}
