// Probe de liveness/readiness do Kubernetes para o container do frontend.
// Não depende da API: só indica que o servidor Next.js está respondendo.
export const dynamic = "force-dynamic";

export function GET(): Response {
  return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
}
