export type RunStatus =
  | "queued"
  | "running"
  | "needs_clarification"
  | "completed"
  | "failed"
  | "cancelled";

export type ResearchRun = {
  run_id: string;
  workspace_id: string;
  status: RunStatus;
  result?: {
    dossier?: Record<string, unknown>;
    strategies?: {
      scenarios?: StrategyScenario[];
      limitations?: string[];
      evidence_count?: number;
    };
    report?: Record<string, unknown>;
  };
  error?: string;
};

export type StrategyScenario = {
  id: string;
  label: string;
  channel: string;
  priority: number;
  premise: string;
  why_fit: string;
  opening_message: string;
  next_step: string;
  requires_validation: boolean;
};

const baseUrl = "";

function headers(workspaceId: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Workspace-ID": workspaceId,
  };
}

export async function createResearch(input: {
  person: string;
  company?: string;
  objective: string;
  location?: string;
  workspaceId: string;
}): Promise<ResearchRun> {
  const response = await fetch(`${baseUrl}/api/research/runs`, {
    method: "POST",
    headers: headers(input.workspaceId),
    body: JSON.stringify({
      person: input.person,
      company: input.company || null,
      objective: input.objective,
      location: input.location || null,
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function getResearch(runId: string, workspaceId: string): Promise<ResearchRun> {
  const response = await fetch(`${baseUrl}/api/research/runs/${runId}`, {
    headers: headers(workspaceId),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
