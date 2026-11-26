import type { Bubble, ThoughtRecord } from "./types";

export interface SpaceNote {
  id: string;
  text: string;
  source: string;
  quote?: string;
  url?: string;
  createdAt?: number;
  articleKey?: string;
  parents?: string[];
  generated?: boolean;
}

export const PAGE_SIZE = 6;
export const sampleNotes: SpaceNote[] = [
  { id: "sample-1", text: "阅读不是把知识装满，而是让原本孤立的想法，慢慢有了联系。", source: "关于阅读", quote: "知识的价值，往往发生在连接之中。" },
  { id: "sample-2", text: "好的问题，不一定立刻有答案。先把它留下来，让生活继续提供线索。", source: "把问题留下来" },
  { id: "sample-3", text: "如果每一次选择都追求最优解，会不会错过那些意料之外的可能？", source: "关于选择" },
  { id: "sample-4", text: "慢一点不是停止。给思考留出空隙，新的理解才有机会出现。", source: "留一点空白" },
  { id: "sample-5", text: "理解一个观点之前，也许应该先理解：它是在怎样的处境里诞生的。", source: "换一个角度" },
  { id: "sample-6", text: "记录自己的疑惑，也是在记录自己与世界相遇的方式。", source: "阅读的余温" },
];

export function fromSavedBubble(bubble: Bubble): SpaceNote {
  return { id: bubble.id, text: bubble.body, source: bubble.title || "阅读手记", quote: bubble.quote,
    url: safeSourceUrl(bubble.source_url), createdAt: bubble.created_at,
    ...(bubble.article_key ? { articleKey: bubble.article_key } : {}) };
}

export function fromThought(record: ThoughtRecord): SpaceNote {
  return fromSavedBubble({
    ...record,
    title: record.source_title || record.title,
    author_name: "",
  });
}

export function safeSourceUrl(value?: string): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && (url.hostname === "zhihu.com" || url.hostname.endsWith(".zhihu.com")) ? url.href : undefined;
  } catch { return undefined; }
}

export function filterNotes(notes: SpaceNote[], query: string, draftsOnly: boolean, folded: Set<string>): SpaceNote[] {
  const needle = query.trim().toLocaleLowerCase();
  return notes.filter(note => !folded.has(note.id) && (!draftsOnly || note.generated)
    && (!needle || `${note.text} ${note.source} ${note.quote || ""}`.toLocaleLowerCase().includes(needle)));
}

// Deliberately authored by the reader: no canned synthesis or implicit server writes.
export function connectionDraft(a: SpaceNote, b: SpaceNote, body: string, id = crypto.randomUUID()): SpaceNote {
  const text = body.trim();
  if (!text || text.length > 4000) throw new Error("请填写 1–4000 字的新观点。");
  if (a.id === b.id || id === a.id || id === b.id) throw new Error("请选择两个不同的想法。");
  return { id, text, source: "我的连接 · 本页草稿", generated: true, parents: [a.id, b.id] };
}

export function sceneItems(notes: SpaceNote[], width = 900, height = 600) {
  const positions = notes.length <= 4 ? [[.26, .31], [.73, .30], [.27, .72], [.74, .71]]
    : [[.26, .29], [.67, .25], [.47, .54], [.80, .72], [.16, .72], [.51, .85]];
  const radius = Math.max(48, Math.min(108, width * (width < 500 ? .18 : .125), height * .18));
  return notes.slice(0, PAGE_SIZE).map((note, index) => ({ ...note, x: positions[index][0], y: positions[index][1], radius: radius * (index === 0 ? 1.08 : .92 + (index % 3) * .04) }));
}
