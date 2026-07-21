import { proxyApi } from "../../../../lib/server-api";

export async function POST(request: Request) {
  return proxyApi("/v1/research/runs", request);
}

export async function GET(request: Request) {
  const query = new URL(request.url).search;
  return proxyApi(`/v1/research/runs${query}`, request);
}
