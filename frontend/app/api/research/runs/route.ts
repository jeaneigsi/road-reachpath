import { proxyApi } from "../../../../lib/server-api";

export async function POST(request: Request) {
  return proxyApi("/v1/research/runs", request);
}
