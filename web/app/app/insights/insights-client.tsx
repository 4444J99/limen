"use client";

import React, { useEffect, useMemo, useState } from "react";
import SurfaceNav from "../surface-nav";

export interface Insight {
  id: string;
  severity: "critical" | "warning" | "info" | "low";
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

export default function InsightsClient() {
  const [reports, setReports] = useState<InsightReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchInsights() {
      try {
        setLoading(true);
        // Fetch all tier JSON files in parallel (was serial for-loop).
        const tiers = ["hourly", "daily", "weekly", "monthly"] as const;
        const results = await Promise.all(
          tiers.map(async (tier) => {
            try {
              const res = await fetch(`/${tier}-insights.json`);
              if (res.ok) return (await res.json()) as InsightReport;
            } catch {
              // Ignore missing tiers
            }
            return null;
          })
        );
        setReports(results.filter((r): r is InsightReport => r !== null));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load insights");
      } finally {
        setLoading(false);
      }
    }

    fetchInsights();
  }, []);

  const { aggregatedInsights, ownerGroups } = useMemo(() => {
    const allInsights = reports.flatMap(r => r.insights);
    
    const groups: Record<string, Insight[]> = {};
    for (const insight of allInsights) {
      if (!groups[insight.owner]) {
        groups[insight.owner] = [];
      }
      groups[insight.owner].push(insight);
    }
    
    return {
      aggregatedInsights: allInsights,
      ownerGroups: groups,
    };
  }, [reports]);

  return (
    <main className="dashboard-main">
      <SurfaceNav active="insights" persona="owner" />
      
      <header className="pageHeader">
        <h1>Insights Dashboard</h1>
        <p>Read-only aggregate of cadence insights across the organ fleet.</p>
      </header>

      {loading && <p>Loading insights...</p>}
      {error && <div className="panel errorPanel"><p>{error}</p></div>}

      {!loading && !error && reports.length === 0 && (
        <div className="panel">
          <p>No insights found for any cadence.</p>
        </div>
      )}

      {!loading && reports.length > 0 && (
        <div className="insightsGrid">
          {Object.entries(ownerGroups).map(([owner, insights]) => (
            <div key={owner} className="panel ownerPanel">
              <header className="panelHeader">
                <h2>{owner === "anthony" ? "Human Action Required (Anthony)" : owner}</h2>
                <div className="metricBadge">
                  {insights.length} insight{insights.length !== 1 ? 's' : ''}
                </div>
              </header>
              <div className="insightList">
                {insights.map((insight) => (
                  <div key={insight.id} className={`insightItem severity-${insight.severity}`}>
                    <div className="insightHeader">
                      <span className={`statusBadge ${insight.severity}`}>{insight.severity}</span>
                      <strong>{insight.title}</strong>
                      {insight.healable && <span className="healableBadge">Healable</span>}
                    </div>
                    <p className="insightDetail">{insight.detail}</p>
                    <div className="insightMeta">
                      <span className="sourceLabel">Source: {insight.source}</span>
                    </div>
                    {insight.suggested_action && (
                      <div className="actionBox">
                        <strong>Suggested Action:</strong> {insight.suggested_action}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      
      <style dangerouslySetInnerHTML={{ __html: `
        .insightsGrid {
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
          margin-top: 1.5rem;
        }
        .ownerPanel {
          border-left: 4px solid var(--accent-color, #4a90e2);
        }
        .insightList {
          display: flex;
          flex-direction: column;
          gap: 1rem;
          margin-top: 1rem;
        }
        .insightItem {
          padding: 1rem;
          background: var(--bg-surface, #1e1e1e);
          border: 1px solid var(--border-color, #333);
          border-radius: 4px;
        }
        .insightItem.severity-critical {
          border-left: 4px solid var(--color-critical, #e74c3c);
        }
        .insightItem.severity-warning {
          border-left: 4px solid var(--color-warning, #f39c12);
        }
        .insightHeader {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          margin-bottom: 0.5rem;
        }
        .statusBadge {
          font-size: 0.7rem;
          text-transform: uppercase;
          padding: 0.15rem 0.4rem;
          border-radius: 3px;
          font-weight: 600;
        }
        .statusBadge.critical { background: rgba(231, 76, 60, 0.2); color: #ff6b6b; }
        .statusBadge.warning { background: rgba(243, 156, 18, 0.2); color: #feca57; }
        .statusBadge.info { background: rgba(52, 152, 219, 0.2); color: #54a0ff; }
        .statusBadge.low { background: rgba(149, 165, 166, 0.2); color: #c8d6e5; }
        .healableBadge {
          font-size: 0.7rem;
          background: rgba(46, 204, 113, 0.2);
          color: #2ecc71;
          padding: 0.15rem 0.4rem;
          border-radius: 3px;
          margin-left: auto;
        }
        .insightDetail {
          font-size: 0.9rem;
          color: var(--text-secondary, #aaa);
          margin-bottom: 0.5rem;
        }
        .insightMeta {
          font-size: 0.8rem;
          color: var(--text-tertiary, #777);
          margin-bottom: 0.75rem;
        }
        .actionBox {
          background: rgba(255, 255, 255, 0.05);
          padding: 0.75rem;
          border-radius: 4px;
          font-size: 0.9rem;
          border-left: 2px solid var(--text-secondary, #aaa);
        }
      `}} />
    </main>
  );
}
