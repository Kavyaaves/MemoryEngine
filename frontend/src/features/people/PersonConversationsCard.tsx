import { MessagesSquare } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/EmptyState";
import type { PersonConversation } from "@/types/api";
import { formatNumber } from "@/lib/format";

/** Conversations with this person, biggest first, each with a bar proportional to its size. */
export function PersonConversationsCard({ conversations }: { conversations: PersonConversation[] }) {
  const sorted = [...conversations].sort((a, b) => b.memory_count - a.memory_count);
  const largest = Math.max(1, ...sorted.map((conversation) => conversation.memory_count));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MessagesSquare className="size-4" aria-hidden /> Conversations
        </CardTitle>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <EmptyState title="No conversations" className="py-6" />
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {sorted.map((conversation) => (
              <li key={conversation.id} className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="memory-text min-w-0 flex-1 truncate" title={conversation.title}>
                    {conversation.title || "Untitled conversation"}
                  </span>
                  <span className="tabular-nums text-muted-foreground">{formatNumber(conversation.memory_count)}</span>
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary/60"
                    style={{ width: `${(conversation.memory_count / largest) * 100}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
