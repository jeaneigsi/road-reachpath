import { proxyApi } from "../../../../../lib/server-api";

export async function GET(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return proxyApi(`/v1/research/runs/${encodeURIComponent(runId)}`, request);
}
