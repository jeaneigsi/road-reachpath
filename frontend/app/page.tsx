"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { clarifyResearch, createResearch, getResearch, listResearch, ResearchRun, RunStatus, StrategyScenario } from "../lib/api";

const phases: { key: RunStatus; label: string }[] = [
  { key: "queued", label: "Queued" },
  { key: "running", label: "Researching" },
  { key: "needs_clarification", label: "Needs context" },
  { key: "completed", label: "Ready" },
];

function statusIndex(status?: RunStatus) {
  if (status === "failed" || status === "cancelled") return -1;
  return phases.findIndex((phase) => phase.key === status);
}

export default function Home() {
  const [person, setPerson] = useState("");
  const [sourcePerson, setSourcePerson] = useState("");
  const [company, setCompany] = useState("");
  const [objective, setObjective] = useState("");
  const [location, setLocation] = useState("");
  const [workspaceId] = useState("local");
  const [run, setRun] = useState<ResearchRun>();
  const [history, setHistory] = useState<ResearchRun[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!run || ["completed", "needs_clarification", "failed", "cancelled"].includes(run.status)) return;
    const timer = window.setInterval(async () => {
      try {
        setRun(await getResearch(run.run_id, workspaceId));
      } catch (pollError) {
        setError(pollError instanceof Error ? pollError.message : "Unable to read the run");
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [run, workspaceId]);

  useEffect(() => {
    listResearch(workspaceId).then(setHistory).catch(() => undefined);
  }, [workspaceId]);

  const scenarios = useMemo<StrategyScenario[]>(
    () => run?.result?.strategies?.scenarios ?? [],
    [run],
  );
  const paths = run?.result?.dossier?.relationship_paths ?? [];
  const contactStrategy = run?.result?.dossier?.contact_strategy;
  const claims = run?.result?.dossier?.claims ?? [];
  const evidence = run?.result?.dossier?.evidence ?? [];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!person.trim() || !objective.trim()) return;
    setIsSubmitting(true);
    setError(undefined);
    try {
      const created = await createResearch({ person, sourcePerson, company, objective, location, workspaceId });
      setRun(created);
      setHistory((current) => [created, ...current.filter((item) => item.run_id !== created.run_id)]);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to start research");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function clarify() {
    if (!run) return;
    setIsSubmitting(true);
    setError(undefined);
    try {
      const clarified = await clarifyResearch(run.run_id, { person, sourcePerson, company, objective, location, workspaceId });
      setRun(clarified);
      setHistory((current) => [clarified, ...current.filter((item) => item.run_id !== clarified.run_id)]);
    } catch (clarifyError) {
      setError(clarifyError instanceof Error ? clarifyError.message : "Unable to resume research");
    } finally {
      setIsSubmitting(false);
    }
  }

  const currentPhase = statusIndex(run?.status);
  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand-mark"><span>R</span><div><strong>ReachPath</strong><small>Prospect intelligence</small></div></div>
        <nav aria-label="Primary navigation">
          <a className="nav-link active" href="#new-path"><span className="nav-index">01</span>New path</a>
          <a className="nav-link" href="#history"><span className="nav-index">02</span>History</a>
          <a className="nav-link" href="#connections"><span className="nav-index">03</span>Connections</a>
          <a className="nav-link" href="#reports"><span className="nav-index">04</span>Reports</a>
        </nav>
        <div className="sidebar-note"><span className="status-dot" />Workspace / local<small>Public and authorised data only</small></div>
      </aside>

      <section className="content" id="new-path">
        <header className="topbar"><span>ReachPath / New path</span><button className="quiet-button" type="button">Documentation ↗</button></header>
        <div className="intro"><p className="eyebrow">RELATIONSHIP INTELLIGENCE</p><h1>Find the path<br /><em>in.</em></h1><p className="lede">A sourced view of the person, the context around them, and the most credible way to start a conversation.</p></div>

        <div className="workspace-grid">
          <form className="research-form" onSubmit={submit}>
            <div className="form-heading"><span className="step-number">01</span><div><h2>Define your target</h2><p>Start with what you know. We will surface what needs verifying.</p></div></div>
            <label>Person <input value={person} onChange={(event) => setPerson(event.target.value)} placeholder="e.g. Nadia Karim" required /></label>
            <label>Your professional starting point <input value={sourcePerson} onChange={(event) => setSourcePerson(event.target.value)} placeholder="Optional — who can make the introduction?" /></label>
            <div className="form-row"><label>Company <input value={company} onChange={(event) => setCompany(event.target.value)} placeholder="Optional" /></label><label>Location <input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Optional" /></label></div>
            <label>What are you trying to achieve? <textarea value={objective} onChange={(event) => setObjective(event.target.value)} placeholder="e.g. Find an introduction for a partnership conversation" required rows={4} /></label>
            <div className="form-footer"><span className="privacy-note">⌁ Sources remain visible<br />throughout the dossier.</span><button className="primary-button" disabled={isSubmitting}>{isSubmitting ? "Starting…" : "Start research"}<span>→</span></button></div>
          </form>

          <aside className="run-panel" aria-live="polite">
            <div className="panel-kicker">CURRENT RUN</div>
            {!run && <div className="empty-panel"><div className="orbit" /><h3>Nothing in motion</h3><p>Your next research path will appear here. It stays private to this workspace until you choose to share it.</p></div>}
            {run && <><div className="run-target"><span>Target</span><strong>{person}</strong>{company && <small>{company}</small>}</div><div className="phase-list">{phases.map((phase, index) => <div className={`phase ${index <= currentPhase ? "done" : ""} ${phase.key === run.status ? "current" : ""}`} key={phase.key}><span className="phase-marker">{index < currentPhase ? "✓" : String(index + 1).padStart(2, "0")}</span><span>{phase.label}</span>{phase.key === run.status && <small>now</small>}</div>)}</div>{run.status === "failed" && <div className="error-box">{run.error ?? "Research failed"}</div>}{run.status === "needs_clarification" && <><div className="error-box">Identity context is needed before a reliable dossier can be generated. Update the fields and retry.</div><button className="secondary-button" type="button" onClick={clarify} disabled={isSubmitting}>Retry with context →</button></>}{run.status === "completed" && <div className="ready-box"><span>●</span><div><strong>Dossier ready</strong><small>Evidence and strategy are available below.</small></div></div>}</>}
          </aside>
        </div>

        {error && <div className="error-box global-error">{error}</div>}
        {run?.status === "completed" && paths.length > 0 && <section className="paths-summary" id="connections"><div><p className="eyebrow">VERIFIED ROUTES</p><h2>{paths.length} professional path{paths.length > 1 ? "s" : ""} found.</h2><p>Ranked by ARGUS using relationship strength, confidence and hop depth.</p></div><div className="path-list">{paths.slice(0, 3).map((path, index) => <div className="path-row" key={`${path.degree ?? index}-${index}`}><span className="path-rank">0{index + 1}</span><strong>{path.degree ?? "?"} hop{path.degree === 1 ? "" : "s"}</strong><span>{Math.round((path.introduction_confidence ?? 0) * 100)}% confidence · {path.introduction_risk ?? "review"} risk</span></div>)}</div>{contactStrategy?.recommendation && <div className="path-recommendation">Recommendation: <strong>{contactStrategy.recommendation.replaceAll("_", " ")}</strong></div>}</section>}
        {run?.status === "completed" && <section className="evidence-ledger" id="evidence"><div className="ledger-heading"><div><p className="eyebrow">EVIDENCE LEDGER</p><h2>What the dossier can support.</h2></div><span>{evidence.length} source{evidence.length === 1 ? "" : "s"}</span></div>{claims.length > 0 ? <div className="claim-list">{claims.slice(0, 12).map((claim) => <article className="claim-row" key={claim.id}><span className={`claim-state ${claim.status ?? "open"}`}>{claim.status ?? "open"}</span><div><strong>{claim.text}</strong><small>{Math.round((claim.confidence ?? 0) * 100)}% confidence · {claim.evidence_ids?.length ?? 0} linked source{claim.evidence_ids?.length === 1 ? "" : "s"}</small></div></article>)}</div> : <p className="empty-ledger">No externally verified claims were returned for this run. Treat the generated scenarios as hypotheses only.</p>}{evidence.length > 0 && <div className="source-list">{evidence.slice(0, 8).map((source) => <a href={source.url} target="_blank" rel="noreferrer" key={source.id}><span>{source.source_type ?? "source"}</span><strong>{source.title || source.url}</strong><small>{source.snippet || "Open source"}</small></a>)}</div>}</section>}
        {run?.status === "completed" && <section className="results" id="reports"><div className="results-heading"><div><p className="eyebrow">THE FIRST CONVERSATION</p><h2>Three ways forward.</h2></div><span className="confidence-chip">Human review required</span></div><div className="scenario-grid">{scenarios.map((scenario, index) => <article className={`scenario-card ${index === 0 ? "featured" : ""}`} key={scenario.id}><div className="scenario-top"><span>0{index + 1}</span><small>{scenario.channel.replaceAll("_", " ")}</small></div><h3>{scenario.label}</h3><p>{scenario.premise}</p><blockquote>“{scenario.opening_message}”</blockquote><div className="scenario-next"><span>Next step</span><strong>{scenario.next_step}</strong></div></article>)}</div><div className="result-foot"><span>Evidence count: {run.result?.strategies?.evidence_count ?? 0}</span><span>Generated hypotheses are editable — nothing is sent automatically.</span></div></section>}
        <section className="history-panel" id="history"><div className="ledger-heading"><div><p className="eyebrow">WORKSPACE HISTORY</p><h2>Recent paths.</h2></div><span>{history.length} run{history.length === 1 ? "" : "s"}</span></div><div className="history-list">{history.slice(0, 12).map((item) => <button type="button" className={`history-row ${item.run_id === run?.run_id ? "selected" : ""}`} key={item.run_id} onClick={() => { setRun(item); setPerson(item.request.person); setCompany(item.request.company ?? ""); setSourcePerson(item.request.source_person ?? ""); setObjective(item.request.objective); setLocation(item.request.location ?? ""); }}><span>{item.status.replaceAll("_", " ")}</span><strong>{item.request.person}</strong><small>{item.request.objective}</small></button>)}</div></section>
      </section>
    </main>
  );
}
