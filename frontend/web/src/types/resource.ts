export interface ResourcePackage {
  lecture?: { title?: string; markdown?: string; content?: string };
  example?: { title?: string; markdown?: string; content?: string };
  practice?: { title?: string; markdown?: string; content?: string };
  quiz?: { title?: string; markdown?: string; content?: string; questions?: unknown[] };
  [key: string]: unknown;
}
