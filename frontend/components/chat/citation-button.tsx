import type { Source } from "@/lib/api/types";

export function describeSource(source: Source): string {
  return `${source.filename}, página ${source.page}`;
}

export interface CitationButtonProps {
  source: Source;
  onOpen: (source: Source) => void;
}

/**
 * Clickable `[n]` citation. The accessible name starts with the visible text
 * (WCAG 2.5.3) and adds the file and page for screen reader users.
 */
export function CitationButton({ source, onOpen }: CitationButtonProps) {
  return (
    <button
      type="button"
      onClick={() => onOpen(source)}
      className="mx-0.5 rounded-sm px-0.5 align-baseline text-sm font-semibold text-primary underline underline-offset-2 hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      [{source.ref}]<span className="sr-only"> ver fonte: {describeSource(source)}</span>
    </button>
  );
}

export type ContentSegment = { kind: "text"; text: string } | { kind: "citation"; sources: Source[]; raw: string };

const CITATION_PATTERN = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

/**
 * Splits an answer into text and citations. Accepts `[1]` and `[1, 2]`; references
 * without a matching source stay as plain text (never a dead button).
 */
export function splitCitations(text: string, sources: Source[]): ContentSegment[] {
  const byRef = new Map(sources.map((s) => [s.ref, s]));
  const segments: ContentSegment[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION_PATTERN)) {
    const refs = (match[1] ?? "").split(",").map((n) => Number(n.trim()));
    const found = refs.map((n) => byRef.get(n));
    if (found.some((s) => s === undefined)) continue;
    const index = match.index ?? 0;
    if (index > last) segments.push({ kind: "text", text: text.slice(last, index) });
    segments.push({ kind: "citation", sources: found as Source[], raw: match[0] });
    last = index + match[0].length;
  }
  if (last < text.length) segments.push({ kind: "text", text: text.slice(last) });
  return segments;
}

export interface AnswerContentProps {
  text: string;
  sources: Source[];
  onOpenSource: (source: Source) => void;
}

/** Plain-text rendering (no HTML injection); citations become buttons. */
export function AnswerContent({ text, sources, onOpenSource }: AnswerContentProps) {
  return (
    <p className="whitespace-pre-wrap break-words leading-relaxed">
      {splitCitations(text, sources).map((segment, index) =>
        segment.kind === "text" ? (
          <span key={index}>{segment.text}</span>
        ) : (
          <span key={index}>
            {segment.sources.map((source) => (
              <CitationButton key={source.ref} source={source} onOpen={onOpenSource} />
            ))}
          </span>
        ),
      )}
    </p>
  );
}
