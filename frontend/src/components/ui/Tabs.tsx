// A row of tab buttons for switching views (Life: 3D/List, Media: Photos/Audio/Video).
// Usage:
//   <Tabs value={view} onValueChange={setView}>
//     <TabsList><TabsTrigger value="3d">3D</TabsTrigger>…</TabsList>
//   </Tabs>
// The parent owns the selected value; the triggers read it through React context.
import { createContext, useContext, useRef, type ComponentProps, type KeyboardEvent } from "react";
import { cn } from "@/lib/cn";

interface TabsContextValue {
  value: string;
  onValueChange: (value: string) => void;
}
const TabsContext = createContext<TabsContextValue | null>(null);

interface TabsProps extends Omit<ComponentProps<"div">, "onChange"> {
  value: string;
  onValueChange: (value: string) => void;
}

export function Tabs({ value, onValueChange, className, ...props }: TabsProps) {
  return (
    <TabsContext.Provider value={{ value, onValueChange }}>
      <div className={cn("flex flex-col gap-3", className)} {...props} />
    </TabsContext.Provider>
  );
}

export function TabsList({ className, ...props }: ComponentProps<"div">) {
  const listRef = useRef<HTMLDivElement>(null);

  // Left/right arrow keys move between tabs (the standard keyboard pattern for a tab list).
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const tabs = Array.from(listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]:not([disabled])') ?? []);
    const currentIndex = tabs.findIndex((tab) => tab === document.activeElement);
    if (currentIndex === -1) return;
    const step = event.key === "ArrowRight" ? 1 : -1;
    const nextTab = tabs[(currentIndex + step + tabs.length) % tabs.length];
    nextTab?.focus();
    nextTab?.click();
  };

  return (
    <div
      ref={listRef}
      role="tablist"
      onKeyDown={onKeyDown}
      className={cn(
        "inline-flex h-9 w-fit max-w-full items-center gap-1 overflow-x-auto rounded-lg bg-muted p-1 text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

interface TabsTriggerProps extends ComponentProps<"button"> {
  value: string;
}

export function TabsTrigger({ value, className, ...props }: TabsTriggerProps) {
  const tabs = useContext(TabsContext);
  if (!tabs) throw new Error("<TabsTrigger> must be used inside <Tabs>");
  const selected = tabs.value === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      // Only the selected tab is in the Tab order; the arrow keys reach the others.
      tabIndex={selected ? 0 : -1}
      onClick={() => tabs.onValueChange(value)}
      className={cn(
        "inline-flex cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4",
        selected ? "bg-background text-foreground shadow-sm" : "hover:text-foreground",
        className,
      )}
      {...props}
    />
  );
}
