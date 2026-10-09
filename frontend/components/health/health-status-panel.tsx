import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DEPENDENCIES, type DependencyCheck, type ReadinessResponse } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const DEPENDENCY_LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  redis: "Redis",
  qdrant: "Qdrant",
  s3: "Armazenamento S3",
  litellm: "LiteLLM",
};

const latencyFormatter = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const timeFormatter = new Intl.DateTimeFormat("pt-BR", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

export function formatLatency(latencyMs: number | null | undefined): string {
  if (latencyMs === null || latencyMs === undefined || !Number.isFinite(latencyMs)) return "—";
  return `${latencyFormatter.format(latencyMs)} ms`;
}

interface DependencyRow {
  name: string;
  label: string;
  check: DependencyCheck | undefined;
}

function buildRows(checks: ReadinessResponse["checks"]): DependencyRow[] {
  const extras = Object.keys(checks).filter((key) => !(DEPENDENCIES as readonly string[]).includes(key));
  return [...DEPENDENCIES, ...extras].map((name) => ({
    name,
    label: DEPENDENCY_LABELS[name] ?? name,
    check: checks[name],
  }));
}

function StatusBadge({ check }: { check: DependencyCheck | undefined }) {
  // Estado comunicado por texto e símbolo, não apenas por cor (WCAG 1.4.1).
  if (!check) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-input px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
        <span aria-hidden="true">?</span>
        Não informado
      </span>
    );
  }
  const ok = check.status === "ok";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        ok ? "bg-success text-success-foreground" : "bg-destructive text-destructive-foreground",
      )}
    >
      <span aria-hidden="true">{ok ? "✓" : "✕"}</span>
      {ok ? "Operacional" : "Com erro"}
    </span>
  );
}

export interface HealthStatusPanelProps {
  data: ReadinessResponse | null;
  error: string | null;
  isLoading: boolean;
  isRefreshing: boolean;
  lastUpdated: Date | null;
  onRefresh: () => void;
}

export function HealthStatusPanel({
  data,
  error,
  isLoading,
  isRefreshing,
  lastUpdated,
  onRefresh,
}: HealthStatusPanelProps) {
  const summary = isLoading
    ? "Verificando o ambiente…"
    : error && !data
      ? "Não foi possível verificar o ambiente."
      : data?.status === "ok"
        ? "Todos os serviços estão operacionais."
        : "Ambiente degradado: um ou mais serviços apresentam erro.";

  return (
    <section aria-labelledby="health-title" aria-busy={isLoading || isRefreshing}>
    <Card>
      <CardHeader className="sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="flex flex-col gap-1.5">
          <CardTitle id="health-title">Status do ambiente</CardTitle>
          <CardDescription>Atualização automática a cada 15 segundos.</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={isRefreshing} className="mt-2 sm:mt-0">
          {isRefreshing ? "Atualizando…" : "Atualizar agora"}
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* Região viva: leitores de tela só anunciam quando o resumo muda. */}
        <p role="status" aria-live="polite" className="text-sm font-medium">
          {summary}
        </p>

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
            {data && " Exibindo o último resultado obtido."}
          </p>
        )}

        {data && (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Serviços do ambiente">
            {buildRows(data.checks).map(({ name, label, check }) => (
              <li key={name} className="flex flex-col gap-2 rounded-md border p-4" data-testid={`dependency-${name}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-base font-semibold">{label}</h3>
                  <StatusBadge check={check} />
                </div>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  <dt className="text-muted-foreground">Latência</dt>
                  <dd>{formatLatency(check?.latency_ms)}</dd>
                  <dt className="text-muted-foreground">Detalhe</dt>
                  <dd className="break-words">{check?.detail ?? "—"}</dd>
                </dl>
              </li>
            ))}
          </ul>
        )}

        {lastUpdated && (
          <p className="text-xs text-muted-foreground">
            Última verificação às <time dateTime={lastUpdated.toISOString()}>{timeFormatter.format(lastUpdated)}</time>
          </p>
        )}
      </CardContent>
    </Card>
    </section>
  );
}
