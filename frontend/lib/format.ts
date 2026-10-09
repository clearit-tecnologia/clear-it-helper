// pt-BR display formatters (dates as dd/mm/aaaa).

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const sizeFormatter = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const scoreFormatter = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const integerFormatter = new Intl.NumberFormat("pt-BR");

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : dateTimeFormatter.format(date);
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${integerFormatter.format(bytes)} B`;
  if (bytes < 1024 * 1024) return `${sizeFormatter.format(bytes / 1024)} KB`;
  return `${sizeFormatter.format(bytes / (1024 * 1024))} MB`;
}

export function formatScore(score: number): string {
  return Number.isFinite(score) ? scoreFormatter.format(score) : "—";
}

export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : integerFormatter.format(value);
}
