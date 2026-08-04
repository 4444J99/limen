"use client";

import React, { useEffect, useMemo, useState } from "react";
import SurfaceNav from "../surface-nav";

type Severity = "critical" | "warning" | "info" | "low";

export interface Insight {
  id: string;
  severity: Severity;
  title: string;
  detail: string;
  owner: string;
  source: string;
  suggested_action: string;
  healable: boolean;
}

export interface InsightReport {
  tier: "hourly" | "daily" | "weekly" | "monthly";
  generated_at: string;
  window_start: string;
  insights: Insight[];
}

interface RuntimeDashboardTask {
  id: string;
  title: string;
  status: string;
  target_agent: string;
  priority: string;
  repo: string;
  created?: string;
  updated?: string;
  dispatch_log?: Array<{
    timestamp: string;
    status: string;
    agent?: string;
    output?: string;
  }>;
}

interface RuntimeDashboardSnapshot {
  tasks: RuntimeDashboardTask[];
}

interface InsightEnvelope extends Insight {
  generated_at: string;
  window_start: string;
  tier: InsightReport["tier"];
}

interface CommitmentRow {
  id: string;
  summary: string;
  owner: string;
  source: string;
  severity: Severity;
  status: string;
  note: string;
  due?: string;
}

interface TimelineEvent {
  id: string;
  when: string;
  actor: string;
  title: string;
  source: string;
  kind: string;
  severity: Severity;
  detail: string;
}

const SEVERITY_WEIGHT: Record<Severity, number> = {
  critical: 4,
  warning: 3,
  info: 2,
  low: 1,
};

function parseDate(value?: string) {
  if (!value) return null;
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return null;
  return new Date(parsed);
}

function formatDate(value?: string) {
  if (!value) return "Unknown";
  const dt = parseDate(value);
  if (!dt) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(dt);
}

function safeText(value: unknown) {
  if (typeof value !== "string") return "";
  return value;
}

function isSeverity(value: unknown): Severity {
  if (value === "critical" || value === "warning" || value === "info" || value === "low") {
    return value;
  }
  return "low";
}

function safeFetchJson<T>(url: string): Promise<T | null> {
  return fetch(url)
    .then((res) => {
      if (!res.ok) return null;
      return res.json() as Promise<T>;
    })
    .catch(() => null);
}

function highlightText(text: string, query: string) {
  const trimmed = query.trim();
  if (!trimmed) return text;

  const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`(${escaped})`, "ig");
  const parts = text.split(re);
  return parts.map((part, index) => {
    if (part.toLowerCase() === trimmed.toLowerCase()) {
      return <mark className="insightHit" key={`${part}-${index}`}>{part}</mark>;
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function fallbackInsights(): InsightEnvelope[] {
  return [
    {
      id: "fallback-001",
      generated_at: new Date(0).toISOString(),
      window_start: new Date(0).toISOString(),
      tier: "weekly",
      severity: "warning",
      title: "Seeded queue: inbox-to-task bridge under review",
      detail: "The insights cadence fixture is empty, so a synthetic task-bridge item keeps the owner workflows reviewable in a static shell.",
      owner: "anthony",
      source: "inbox/seed-bridge",
      suggested_action: "Review classification policy before auto-routing captures to tasks.",
      healable: true,
    },
    {
      id: "fallback-002",
      generated_at: new Date(0).toISOString(),
      window_start: new Date(0).toISOString(),
      tier: "weekly",
      severity: "info",
      title: "Search and timelines shell remains live",
      detail: "Surface scaffolding is present; add policy tags when live connector data lands.",
      owner: "public",
      source: "insights/surface",
      suggested_action: "Confirm timeline grouping policy and keep this experience review-ready.",
      healable: false,
    },
  ];
}

function parseOwnerFromSource(source: string) {
  const clean = source.trim();
  if (!clean) return "unknown";
  if (clean.includes("/")) {
    const first = clean.split("/").filter(Boolean)[0];
    return first || "unknown";
  }
  return clean;
}

function uniqueSorted(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));
}

function topNBySeverity(rows: InsightEnvelope[], limit = 12) {
  return [...rows]
    .sort((left, right) => {
      const weight = SEVERITY_WEIGHT[right.severity] - SEVERITY_WEIGHT[left.severity];
      if (weight !== 0) return weight;
      return right.generated_at.localeCompare(left.generated_at);
    })
    .slice(0, limit);
}

export default function InsightsClient() {
  const [reports, setReports] = useState<InsightReport[]>([]);
  const [runtime, setRuntime] = useState<RuntimeDashboardSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [ownerFilter, setOwnerFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState<"all" | Severity>("all");
  const [sourceFilter, setSourceFilter] = useState("all");

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const tiers = ["hourly", "daily", "weekly", "monthly"] as const;
        const result = await Promise.all(tiers.map((tier) => safeFetchJson<InsightReport>(`/${tier}-insights.json`)));
        const loadedReports = result.filter(Boolean) as InsightReport[];
        setReports(loadedReports);

        const snapshot = await safeFetchJson<RuntimeDashboardSnapshot>("/dashboard.json");
        if (snapshot?.tasks && Array.isArray(snapshot.tasks)) {
          setRuntime(snapshot);
        } else {
          setRuntime(null);
        }

        if (!loadedReports.length) {
          setError("No cadence insight fixtures were found. Running with synthetic shell data.");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load insight surface data");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  const allInsights = useMemo(() => {
    const merged = reports.flatMap((report) => report.insights.map((insight) => {
      return {
        ...insight,
        id: insight.id || `${report.tier}-${insight.title}`,
        severity: isSeverity(insight.severity),
        title: safeText(insight.title),
        detail: safeText(insight.detail),
        owner: safeText(insight.owner) || "unassigned",
        source: safeText(insight.source),
        generated_at: safeText(report.generated_at),
        window_start: safeText(report.window_start),
        tier: report.tier,
      } satisfies InsightEnvelope;
    }));

    return merged.length ? merged : fallbackInsights();
  }, [reports]);

  const ownerChoices = useMemo(() => uniqueSorted(allInsights.map((insight) => insight.owner)), [allInsights]);
  const sourceChoices = useMemo(() => uniqueSorted(allInsights.map((insight) => insight.source.split("/")[0] || insight.source)), [allInsights]);

  const query = searchQuery.trim().toLowerCase();
  const filteredInsights = useMemo(() => {
    const results = allInsights.filter((item) => {
      const ownerMatch = ownerFilter === "all" || item.owner === ownerFilter;
      const severityMatch = severityFilter === "all" || item.severity === severityFilter;
      const sourceMatch = sourceFilter === "all" || item.source.startsWith(sourceFilter);
      if (!ownerMatch || !severityMatch || !sourceMatch) return false;

      if (!query) return true;
      const haystack = `${item.title} ${item.detail} ${item.owner} ${item.source} ${item.suggested_action}`.toLowerCase();
      return haystack.includes(query);
    });

    return results
      .sort((a, b) => {
        const severityDelta = SEVERITY_WEIGHT[b.severity] - SEVERITY_WEIGHT[a.severity];
        if (severityDelta !== 0) return severityDelta;
        return b.generated_at.localeCompare(a.generated_at);
      })
      .slice(0, 100);
  }, [allInsights, ownerFilter, severityFilter, sourceFilter, query]);

  const activeCommitments = useMemo(() => {
    const items = allInsights.map((insight) => ({
      id: `insight-${insight.id}`,
      summary: insight.title,
      owner: insight.owner,
      source: insight.source,
      severity: insight.severity,
      status: insight.healable ? "healing" : "review",
      note: insight.suggested_action || "Review before action",
      due: insight.generated_at,
    }));

    const fromRuntime = (runtime?.tasks || []).filter((task) => {
      return task.status !== "done" && task.status !== "archived";
    }).map((task) => ({
      id: `task-${task.id}`,
      summary: task.title,
      owner: task.target_agent || "owner",
      source: task.repo || "repo/unknown",
      severity: (task.priority === "high" || task.priority === "critical" ? "critical" : task.priority === "medium" ? "warning" : "info") as Severity,
      status: task.status,
      note: task.dispatch_log?.length ? task.dispatch_log[task.dispatch_log.length - 1]?.status || "in motion" : "Runtime-only action",
      due: task.updated || task.created,
    }));

    const rows = [...items, ...fromRuntime];
    const seen = new Set<string>();
    const deduped: CommitmentRow[] = [];
    for (const row of rows) {
      if (seen.has(row.id)) continue;
      seen.add(row.id);
      deduped.push(row);
    }

    return deduped;
  }, [runtime, allInsights]);

  const waitingRows = useMemo(() => {
    return activeCommitments.filter((item) => item.status === "dispatched" || item.status === "waiting" || item.status === "in_progress");
  }, [activeCommitments]);

  const riskRows = useMemo(() => {
    return activeCommitments.filter((item) => {
      if (item.severity === "critical") return true;
      if (item.severity === "warning" && item.note.toLowerCase().includes("risk")) return true;
      const due = parseDate(item.due || "");
      if (!due) return false;
      const ageHours = (Date.now() - due.getTime()) / (1000 * 60 * 60);
      return ageHours > 48;
    }).slice(0, 40);
  }, [activeCommitments]);

  const meetingBriefs = useMemo(() => {
    const buckets = new Map<string, CommitmentRow[]>();
    for (const item of activeCommitments) {
      const bucket = buckets.get(item.owner) || [];
      bucket.push(item);
      buckets.set(item.owner, bucket);
    }

    return [...buckets.entries()]
      .map(([owner, rows]) => ({
        owner,
        focus: rows.map((item) => item.summary).slice(0, 3),
        open: rows.length,
        critical: rows.filter((item) => item.severity === "critical").length,
      }))
      .sort((a, b) => b.open - a.open)
      .slice(0, 6);
  }, [activeCommitments]);

  const timelineBuckets = useMemo(() => {
    const byPerson = new Map<string, TimelineEvent[]>();
    const byOrg = new Map<string, TimelineEvent[]>();
    const byProject = new Map<string, TimelineEvent[]>();
    const byDecision = new Map<string, TimelineEvent[]>();
    const byEngagement = new Map<string, TimelineEvent[]>();
    const bucketFor = (store: Map<string, TimelineEvent[]>, id: string) => {
      const bucket = store.get(id);
      if (bucket) return bucket;
      const created: TimelineEvent[] = [];
      store.set(id, created);
      return created;
    };

    for (const insight of allInsights) {
      const owner = insight.owner || "unassigned";
      const organization = parseOwnerFromSource(insight.source);
      const project = insight.source || "global";
      const event: TimelineEvent = {
        id: insight.id,
        when: insight.generated_at,
        actor: owner,
        title: insight.title,
        source: insight.source,
        kind: insight.tier,
        severity: insight.severity,
        detail: insight.detail,
      };

      bucketFor(byPerson, owner).push(event);
      bucketFor(byOrg, organization).push(event);
      bucketFor(byProject, project).push(event);

      const lower = `${insight.title} ${insight.detail} ${insight.source}`.toLowerCase();
      const isDecision = lower.includes("decision") || lower.includes("commit") || lower.includes("approve") || lower.includes("approved");
      if (isDecision) {
        const bucket = byDecision.get("decisions") || [];
        bucket.push(event);
        byDecision.set("decisions", bucket);
      }

      const isEngagement = lower.includes("engagement") || lower.includes("task") || lower.includes("work");
      if (isEngagement) {
        const bucket = byEngagement.get("engagement") || [];
        bucket.push(event);
        byEngagement.set("engagement", bucket);
      }
    }

    const sortEvents = (events: TimelineEvent[]) => {
      return [...events]
        .sort((a, b) => b.when.localeCompare(a.when))
        .slice(0, 12)
        .map((entry) => entry);
    };

    const pickBucket = (map: Map<string, TimelineEvent[]>, maxBuckets = 5) => {
      return Array.from(map.entries())
        .map(([id, items]) => ({
          id,
          label: id,
          events: sortEvents(items),
        }))
        .sort((a, b) => b.events.length - a.events.length)
        .slice(0, maxBuckets);
    };

    return {
      byPerson: pickBucket(byPerson),
      byOrg: pickBucket(byOrg),
      byProject: pickBucket(byProject),
      byDecision: pickBucket(byDecision),
      byEngagement: pickBucket(byEngagement),
    };
  }, [allInsights]);

  const totalInsights = allInsights.length;
  const criticalOpen = allInsights.filter((item) => item.severity === "critical").length;
  const warningOpen = allInsights.filter((item) => item.severity === "warning").length;
  const healedHints = allInsights.filter((item) => item.healable).length;

  return (
    <main className="audienceShell insightsShell">
      <SurfaceNav active="insights" persona="owner" />

      <header className="audienceHeader">
        <p className="caption">Owner surface</p>
        <h1>Search, timelines, reviews</h1>
        <p>
          Search across governance insights, stitch person/organization/project timelines, and build
          review-ready meeting prep from a policy-safe synthetic view.
        </p>
      </header>

      {loading && <p className="surfaceLoading">Loading insight fixtures...</p>}
      {error && <div className="surfacePanel insightError">{error}</div>}

      <section className="audienceMetrics">
        <div>
          <span>Total insight items</span>
          <strong>{totalInsights}</strong>
          <p>Across hourly through monthly cadences</p>
        </div>
        <div>
          <span>Critical</span>
          <strong className="criticalText">{criticalOpen}</strong>
          <p>Need owner attention before policy application</p>
        </div>
        <div>
          <span>Warnings</span>
          <strong className="warningText">{warningOpen}</strong>
          <p>Need review or deferred action</p>
        </div>
        <div>
          <span>Review commitments</span>
          <strong>{activeCommitments.length}</strong>
          <p>Healable or open runtime commitments</p>
        </div>
      </section>

      <section className="surfacePanel insightsSearchPanel">
        <div className="panelTitle">
          <span>Global search and filters</span>
          <strong>{healedHints} healable signal(s) seeded</strong>
        </div>

        <div className="insightsControls">
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search title, detail, owner, source..."
            aria-label="Search insights"
          />
          <select value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)} aria-label="Filter by owner">
            <option value="all">All owners</option>
            {ownerChoices.map((owner) => <option key={`owner-${owner}`} value={owner}>{owner}</option>)}
          </select>
          <select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value as "all" | Severity)} aria-label="Filter by severity">
            <option value="all">All severities</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
            <option value="low">Low</option>
          </select>
          <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} aria-label="Filter by source">
            <option value="all">All sources</option>
            {sourceChoices.map((source) => <option key={`source-${source}`} value={source}>{source}</option>)}
          </select>
        </div>

        <div className="insightsRows">
          {filteredInsights.length === 0 ? (
            <p className="surfaceEmpty">No matching insight signals.</p>
          ) : (
            filteredInsights.map((insight) => {
              const reason = [] as string[];
              if (query) {
                const target = query.toLowerCase();
                const lowerTitle = insight.title.toLowerCase();
                const lowerDetail = insight.detail.toLowerCase();
                const lowerOwner = insight.owner.toLowerCase();
                const lowerSource = insight.source.toLowerCase();
                if (lowerTitle.includes(target)) reason.push("title");
                if (lowerDetail.includes(target)) reason.push("detail");
                if (lowerOwner.includes(target)) reason.push("owner");
                if (lowerSource.includes(target)) reason.push("source");
              }

              return (
                <article key={insight.id} className={`insightCard insightSeverity-${insight.severity}`}>
                  <div className="insightRowTop">
                    <span className="insightBadge">{insight.severity}</span>
                    <span className="insightSource">{insight.source}</span>
                    <span className="insightType">{insight.tier} · {insight.generated_at.slice(0, 10)}</span>
                  </div>
                  <h3>{highlightText(insight.title, query)}</h3>
                  <p>{highlightText(insight.detail, query)}</p>
                  <div className="insightMeta">
                    <span>Owner: {insight.owner}</span>
                    <span>Policy: {insight.healable ? "healable" : "read-only"}</span>
                    <span>{formatDate(insight.generated_at)}</span>
                  </div>
                  <p className="insightAction">
                    <strong>Suggested action:</strong> {highlightText(insight.suggested_action, query)}
                  </p>
                  {query ? (
                    <p className="insightReasons">Matched on {reason.length ? reason.join(", ") : "general text"}</p>
                  ) : null}
                </article>
              );
            })
          )}
        </div>
      </section>

      <section className="surfacePanel insightsReviewDashboard">
        <div className="panelTitle">
          <span>Commitment review, waiting, and risk</span>
          <strong>Decision surfaces for operator actions</strong>
        </div>

        <div className="insightsReviewGrid">
          <div className="reviewPanel">
            <div className="panelTitle">
              <span>Commitment queue</span>
              <strong>{activeCommitments.length} tracked commitments</strong>
            </div>
            <div className="insightsList">
              {topNBySeverity(allInsights).length ? (
                topNBySeverity(allInsights).map((commitment) => {
                  const label = activeCommitments.find((row) => row.summary === commitment.title) || {
                    status: "review",
                    note: commitment.suggested_action,
                    id: commitment.id,
                    owner: commitment.owner,
                    source: commitment.source,
                    severity: commitment.severity,
                    due: commitment.generated_at,
                  };
                  return (
                    <div key={label.id} className="reviewItem">
                      <div>
                        <span className="reviewBadge">{label.severity}</span>
                        <strong>{commitment.title}</strong>
                      </div>
                      <p>{label.note || "Review required"}</p>
                      <small>{label.owner} · {label.source} · {formatDate(label.due)}</small>
                    </div>
                  );
                })
              ) : (
                <p className="surfaceEmpty">No commitments to review yet.</p>
              )}
            </div>
          </div>

          <div className="reviewPanel">
            <div className="panelTitle">
              <span>Waiting + risk</span>
              <strong>Execution risk queue</strong>
            </div>
            <div className="insightsList">
              <article className="reviewSubPanel">
                <h4>Waiting queue</h4>
                {waitingRows.length ? (
                  waitingRows.slice(0, 10).map((row) => (
                    <div key={`waiting-${row.id}`} className="reviewItem">
                      <div><span className="reviewBadge amber">{row.severity}</span><strong>{row.summary}</strong></div>
                      <small>{row.owner} · {row.source}</small>
                    </div>
                  ))
                ) : (
                  <p className="surfaceEmpty">No items waiting for explicit release.</p>
                )}
              </article>

              <article className="reviewSubPanel">
                <h4>Risk queue</h4>
                {riskRows.length ? (
                  riskRows.slice(0, 10).map((row) => (
                    <div key={`risk-${row.id}`} className="reviewItem">
                      <div><span className="reviewBadge red">{row.severity}</span><strong>{row.summary}</strong></div>
                      <small>{row.note}</small>
                    </div>
                  ))
                ) : (
                  <p className="surfaceEmpty">No high-risk commitments detected.</p>
                )}
              </article>
            </div>
          </div>
        </div>
      </section>

      <section className="surfacePanel insightsMeetings">
        <div className="panelTitle">
          <span>Meeting briefs</span>
          <strong>Prepare owner sessions with policy-safe grouped agendas</strong>
        </div>
        <div className="meetingGrid">
          {meetingBriefs.length === 0 ? (
            <p className="surfaceEmpty">No upcoming meeting briefs.</p>
          ) : (
            meetingBriefs.map((brief) => (
              <article key={`meeting-${brief.owner}`} className="meetingCard">
                <h4>{brief.owner}</h4>
                <p>{brief.open} open items, {brief.critical} critical</p>
                <ol>
                  {brief.focus.map((item, index) => (
                    <li key={`${brief.owner}-${index}`}>{item}</li>
                  ))}
                </ol>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="surfacePanel insightsTimelinePanel">
        <div className="panelTitle">
          <span>Timelines</span>
          <strong>Person, organization, project, engagement, and decision history</strong>
        </div>

        <div className="timelineGrid">
          <article>
            <h4>People timeline</h4>
            {timelineBuckets.byPerson.length ? timelineBuckets.byPerson.slice(0, 4).map((bucket) => (
              <div className="timelineGroup" key={`person-${bucket.id}`}>
                <strong>{bucket.label}</strong>
                <div className="timelineEvents">
                  {bucket.events.slice(0, 4).map((event) => (
                    <div key={`person-${bucket.id}-${event.id}`} className="timelineEvent">
                      <span>{formatDate(event.when)}</span>
                      <em>{event.kind}</em>
                      <strong>{event.title}</strong>
                      <small>{event.actor} · {event.source}</small>
                    </div>
                  ))}
                </div>
              </div>
            )) : <p className="surfaceEmpty">No person timeline data.</p>}
          </article>

          <article>
            <h4>Organization timeline</h4>
            {timelineBuckets.byOrg.length ? timelineBuckets.byOrg.slice(0, 4).map((bucket) => (
              <div className="timelineGroup" key={`org-${bucket.id}`}>
                <strong>{bucket.label}</strong>
                <div className="timelineEvents">
                  {bucket.events.slice(0, 4).map((event) => (
                    <div key={`org-${bucket.id}-${event.id}`} className="timelineEvent">
                      <span>{formatDate(event.when)}</span>
                      <em>{event.kind}</em>
                      <strong>{event.title}</strong>
                      <small>{event.actor} · {event.source}</small>
                    </div>
                  ))}
                </div>
              </div>
            )) : <p className="surfaceEmpty">No organization timeline data.</p>}
          </article>

          <article>
            <h4>Project timeline</h4>
            {timelineBuckets.byProject.length ? timelineBuckets.byProject.slice(0, 4).map((bucket) => (
              <div className="timelineGroup" key={`project-${bucket.id}`}>
                <strong>{bucket.label}</strong>
                <div className="timelineEvents">
                  {bucket.events.slice(0, 4).map((event) => (
                    <div key={`project-${bucket.id}-${event.id}`} className="timelineEvent">
                      <span>{formatDate(event.when)}</span>
                      <em>{event.kind}</em>
                      <strong>{event.title}</strong>
                      <small>{event.actor} · {event.source}</small>
                    </div>
                  ))}
                </div>
              </div>
            )) : <p className="surfaceEmpty">No project timeline data.</p>}
          </article>

          <article>
            <h4>Decision timeline</h4>
            {timelineBuckets.byDecision.length ? timelineBuckets.byDecision.slice(0, 4).map((bucket) => (
              <div className="timelineGroup" key={`decision-${bucket.id}`}>
                <strong>{bucket.label}</strong>
                <div className="timelineEvents">
                  {bucket.events.slice(0, 4).map((event) => (
                    <div key={`decision-${bucket.id}-${event.id}`} className="timelineEvent">
                      <span>{formatDate(event.when)}</span>
                      <em>{event.kind}</em>
                      <strong>{event.title}</strong>
                      <small>{event.actor} · {event.source}</small>
                    </div>
                  ))}
                </div>
              </div>
            )) : <p className="surfaceEmpty">No decision timeline candidates.</p>}
          </article>

          <article>
            <h4>Engagement timeline</h4>
            {timelineBuckets.byEngagement.length ? timelineBuckets.byEngagement.slice(0, 4).map((bucket) => (
              <div className="timelineGroup" key={`engagement-${bucket.id}`}>
                <strong>{bucket.label}</strong>
                <div className="timelineEvents">
                  {bucket.events.slice(0, 4).map((event) => (
                    <div key={`engagement-${bucket.id}-${event.id}`} className="timelineEvent">
                      <span>{formatDate(event.when)}</span>
                      <em>{event.kind}</em>
                      <strong>{event.title}</strong>
                      <small>{event.actor} · {event.source}</small>
                    </div>
                  ))}
                </div>
              </div>
            )) : <p className="surfaceEmpty">No engagement timeline candidates.</p>}
          </article>
        </div>
      </section>
    </main>
  );
}
