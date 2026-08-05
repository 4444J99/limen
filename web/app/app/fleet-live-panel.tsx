"use client";

import { useEffect, useMemo, useState } from "react";

type FleetTask = {
  id?: string;
  repo?: string;
  title?: string;
};

type FleetLane = {
  done?: number;
  in_flight?: number;
  open?: number;
  live_procs?: number;
  working?: FleetTask[];
};

type FleetStatus = {
  board?: Record<string, number>;
  budget?: {
    spent?: number;
    daily?: number;
  };
  lanes?: Record<string, FleetLane>;
};

type FeedState = {
  data: FleetStatus | null;
  updatedAt: Date | null;
  error: string;
  loading: boolean;
};

const feedPath = "/logs/fleet-status.json";
const laneOrder = [
  "codex",
  "claude",
  "opencode",
  "agy",
  "gemini",
  "jules",
  "copilot",
  "warp",
  "oz",
  "github_actions",
];

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat(undefined).format(value);
}

function completionPct(done: number, total: number) {
  if (total <= 0) return 0;
  return Math.round((done / total) * 100);
}

function formatTime(value: Date | null) {
  if (!value) return "Never";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(value);
}

function sortedLanes(lanes: Record<string, FleetLane> = {}) {
  return Object.entries(lanes).sort((a, b) => {
    const ai = laneOrder.indexOf(a[0]);
    const bi = laneOrder.indexOf(b[0]);
    if (ai === -1 && bi === -1) return a[0].localeCompare(b[0]);
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
}

export default function FleetLivePanel({ pollMs = 10000 }: { pollMs?: number }) {
  const [state, setState] = useState<FeedState>({
    data: null,
    updatedAt: null,
    error: "",
    loading: true,
  });

  useEffect(() => {
    let mounted = true;
    let timer: ReturnType<typeof setInterval> | null = null;

    async function load() {
      try {
        const response = await fetch(feedPath);
        if (!response.ok) {
          throw new Error(response.status === 404 ? "Feed not found" : `Feed returned ${response.status}`);
        }
        const payload = (await response.json()) as FleetStatus;
        if (!payload || typeof payload !== "object" || !payload.lanes) {
          throw new Error("Feed is missing lanes");
        }
        if (!mounted) return;
        setState({
          data: payload,
          updatedAt: new Date(),
          error: "",
          loading: false,
        });
      } catch (error) {
        if (!mounted) return;
        setState((current) => ({
          ...current,
          error: error instanceof Error ? error.message : "Feed unavailable",
          loading: false,
        }));
      }
    }

    load();
    timer = setInterval(load, pollMs);

    return () => {
      mounted = false;
      if (timer) clearInterval(timer);
    };
  }, [pollMs]);

  const data = state.data;
  const lanes = useMemo(() => sortedLanes(data?.lanes), [data]);
  const board = data?.board || {};
  const done = numberValue(board.done);
  const inFlight = numberValue(board.dispatched) + numberValue(board.in_progress);
  const open = numberValue(board.open);
  const total = Object.values(board).reduce((sum, value) => sum + numberValue(value), 0);
  const boardPct = completionPct(done, total);
  const budgetSpent = numberValue(data?.budget?.spent);
  const budgetDaily = numberValue(data?.budget?.daily);
  const feedOnline = Boolean(data && !state.error);

  return (
    <section className="fleetPanel" aria-label="Live fleet status">
      <div className="fleetHeader">
        <div>
          <p className="caption">Live fleet</p>
          <h2>Agent lanes</h2>
        </div>
        <div className="fleetHeaderMeta">
          <span className={`fleetFeedState ${feedOnline ? "online" : "offline"}`}>
            {feedOnline ? "Feed online" : state.error || "Loading feed"}
          </span>
          <span>Updated {formatTime(state.updatedAt)}</span>
        </div>
      </div>

      {!data ? (
        <div className="fleetEmpty">
          <strong>{state.loading ? "Loading fleet feed" : state.error || "Waiting for fleet feed"}</strong>
          <p>Expected static asset: {feedPath}</p>
        </div>
      ) : (
        <>
          <div className="fleetSummary" aria-label="Fleet totals">
            <div>
              <span>Completion</span>
              <strong>{boardPct}%</strong>
              <div className="fleetProgress">
                <span style={{ width: `${boardPct}%` }} />
              </div>
            </div>
            <div>
              <span>Done</span>
              <strong>{formatNumber(done)}</strong>
            </div>
            <div>
              <span>In-flight</span>
              <strong>{formatNumber(inFlight)}</strong>
            </div>
            <div>
              <span>Open</span>
              <strong>{formatNumber(open)}</strong>
            </div>
            <div>
              <span>Budget</span>
              <strong>{budgetDaily ? `${formatNumber(budgetSpent)}/${formatNumber(budgetDaily)}` : "n/a"}</strong>
            </div>
          </div>

          <div className="fleetGrid">
            {lanes.map(([name, lane]) => {
              const laneDone = numberValue(lane.done);
              const laneInFlight = numberValue(lane.in_flight);
              const laneOpen = numberValue(lane.open);
              const laneLiveProcs = numberValue(lane.live_procs);
              const laneTotal = laneDone + laneInFlight + laneOpen;
              const lanePct = completionPct(laneDone, laneTotal);
              const live = laneLiveProcs > 0 || (name === "jules" && laneInFlight > 0);
              const working = lane.working || [];
              const current = working[0];

              return (
                <article className="fleetLane" key={name}>
                  <div className="fleetLaneHeader">
                    <span className={`liveDot ${live ? "live" : "idle"}`} aria-label={live ? "live" : "idle"} />
                    <strong>{name}</strong>
                    <em>{name === "jules" ? "cloud" : `${laneLiveProcs} proc${laneLiveProcs === 1 ? "" : "s"}`}</em>
                  </div>
                  <div className="fleetProgress laneProgress" aria-label={`${name} completion ${lanePct}%`}>
                    <span style={{ width: `${lanePct}%` }} />
                  </div>
                  <div className="fleetCounts">
                    <span><strong>{formatNumber(laneDone)}</strong> done</span>
                    <span><strong>{formatNumber(laneInFlight)}</strong> in-flight</span>
                    <span><strong>{formatNumber(laneOpen)}</strong> open</span>
                  </div>
                  <div className="fleetTask">
                    {current ? (
                      <>
                        <span>Current task</span>
                        <strong>{current.repo || "limen"}</strong>
                        <p>{current.title || current.id || "Untitled task"}</p>
                        {current.id && <em>{current.id}</em>}
                        {working.length > 1 && <small>+{working.length - 1} more in lane</small>}
                      </>
                    ) : (
                      <>
                        <span>Current task</span>
                        <p>No active task reported</p>
                      </>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}
