const baseUrl = (process.env.REACHPATH_API_URL ?? "http://127.0.0.1:8020").replace(/\/$/, "");

export async function proxyApi(path: string, request: Request): Promise<Response> {
  const headers = new Headers({ "Content-Type": "application/json" });
  const workspaceId = request.headers.get("X-Workspace-ID") ?? process.env.REACHPATH_WORKSPACE_ID ?? "local";
  headers.set("X-Workspace-ID", workspaceId);
  const apiKey = process.env.REACHPATH_API_KEY;
  if (apiKey) headers.set("Authorization", `Bearer ${apiKey}`);

  const upstream = await fetch(`${baseUrl}${path}`, {
    method: request.method,
    headers,
    body: request.method === "GET" ? undefined : await request.text(),
    cache: "no-store",
  });
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}
