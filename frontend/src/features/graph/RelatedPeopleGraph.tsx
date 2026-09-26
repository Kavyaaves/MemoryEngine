// A small radial "ego graph" in plain SVG: the person in the centre, the people most connected
// to them around it. Thicker, darker lines = stronger relationship (higher weight).
// Clicking a node opens that person; keyboard users get the same links in the list under the graph.
import { useNavigate } from "react-router";
import type { RelatedPerson } from "@/types/api";

const SIZE = 320;
const CENTER = SIZE / 2;
const ORBIT_RADIUS = 115;
const MAX_NODES = 12;

function shorten(name: string, maxLength: number): string {
  return name.length > maxLength ? `${name.slice(0, maxLength - 1)}…` : name;
}

export function RelatedPeopleGraph({ centerName, related }: { centerName: string; related: RelatedPerson[] }) {
  const navigate = useNavigate();
  const strongest = [...related].sort((a, b) => b.weight - a.weight).slice(0, MAX_NODES);
  if (strongest.length === 0) return null;

  const maxWeight = Math.max(...strongest.map((person) => person.weight), 1e-9);
  const nodes = strongest.map((person, index) => {
    // Spread evenly around the circle, starting at 12 o'clock.
    const angle = (index / strongest.length) * Math.PI * 2 - Math.PI / 2;
    return {
      person,
      x: CENTER + ORBIT_RADIUS * Math.cos(angle),
      y: CENTER + ORBIT_RADIUS * Math.sin(angle),
      strength: person.weight / maxWeight, // 0..1
    };
  });

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="mx-auto w-full max-w-xs"
      role="img"
      aria-label={`${centerName} and related people: ${strongest.map((person) => person.display_name).join(", ")}`}
    >
      {nodes.map(({ person, x, y, strength }) => (
        <line
          key={`line-${person.id}`}
          x1={CENTER}
          y1={CENTER}
          x2={x}
          y2={y}
          className="stroke-primary"
          strokeOpacity={0.2 + 0.6 * strength}
          strokeWidth={1 + 3 * strength}
        />
      ))}

      <circle cx={CENTER} cy={CENTER} r={26} className="fill-primary" />
      <text x={CENTER} y={CENTER} dy="0.35em" textAnchor="middle" className="fill-primary-foreground text-[11px] font-semibold">
        {shorten(centerName, 10)}
      </text>

      {nodes.map(({ person, x, y, strength }) => {
        const nodeRadius = 8 + 8 * strength;
        return (
          <g key={person.id} className="cursor-pointer" onClick={() => navigate(`/people/${person.id}`)}>
            <title>
              {person.display_name} (weight {person.weight.toFixed(2)})
            </title>
            <circle cx={x} cy={y} r={nodeRadius} className="fill-card stroke-primary hover:fill-accent" strokeWidth={1.5} />
            <text x={x} y={y + nodeRadius + 11} textAnchor="middle" className="fill-muted-foreground text-[10px]">
              {shorten(person.display_name, 12)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
