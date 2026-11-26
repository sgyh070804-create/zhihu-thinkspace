import { api } from "./api";
import type { ThoughtRecord } from "./types";

export const thoughtModes = [
  { label: "思维泡泡", path: "/thought-bubbles" },
  { label: "思想树", path: "/thought-branches" },
  { label: "长桌讨论", path: "/space/debate" },
];

export function thoughtLink(path: string, id: string) {
  return `${path}?thought=${encodeURIComponent(id)}`;
}

export function saveThought(
  input: {
    body: string;
    title?: string;
    source_url?: string;
    kind?: Exclude<ThoughtRecord["kind"], "reading">;
    parent_ids?: string[];
  },
  requestId: string,
  signal?: AbortSignal,
) {
  return api<ThoughtRecord>("/thoughts", {
    method: "POST",
    body: JSON.stringify({ ...input, request_id: requestId }),
    signal,
  });
}
