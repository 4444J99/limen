"use client";

import { useMemo, useState } from "react";
import type { CorpusStatusData } from "../lib/data";

type Unit = CorpusStatusData["units"][number];
type Comparison = CorpusStatusData["comparisons"][number];

function entries(record: Record<string, number>, limit = 8) {
  return Object.entries(record || {})
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit);
}

function shortId(value?: string | null) {
  if (!value) return "none";
  return value.length > 14 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function formatNumber(value: number | undefined) {
  return Number(value || 0).toLocaleString();
}

function dateLabel(value?: string | null) {
  if (!value) return "undated";
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(time));
}

export default function CorpusCommandCenterClient({ data }: { data: CorpusStatusData }) {
  const laneOptions = useMemo(() => entries(data.coverage.lanes, 30).map(([lane]) => lane), [data.coverage.lanes]);
  const kindOptions = useMemo(() => entries(data.coverage.kinds, 20).map(([kind]) => kind), [data.coverage.kinds]);
  const [lane, setLane] = useState("all");
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedComparisonId, setSelectedComparisonId] = useState(data.comparisons[0]?.comparison_id || "");

  const filteredUnits = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.units
      .filter((unit) => lane === "all" || unit.lane_id === lane)
      .filter((unit) => kind === "all" || unit.kind === kind)
      .filter((unit) => {
        if (!q) return true;
        return [
          unit.unit_id,
          unit.cluster_id,
          unit.source,
          unit.lane_id,
          unit.kind,
          unit.artifact_path || "",
        ].some((value) => value.toLowerCase().includes(q));
      })
      .slice(0, 220);
  }, [data.units, kind, lane, query]);

  const selectedComparison = useMemo<Comparison | undefined>(
    () => data.comparisons.find((item) => item.comparison_id === selectedComparisonId) || data.comparisons[0],
    [data.comparisons, selectedComparisonId],
  );

  const unitsById = useMemo(() => {
    const byId: Record<string, Unit> = {};
    for (const unit of data.units) byId[unit.unit_id] = unit;
    return byId;
  }, [data.units]);

  const leftUnit = selectedComparison ? unitsById[selectedComparison.left_unit_id] : undefined;
  const rightUnit = selectedComparison ? unitsById[selectedComparison.right_unit_id] : undefined;

  return (
    <div className="corpusGrid">
      <section className="corpusPanel corpusPanelWide">
        <div className="corpusPanelHeader">
          <div>
            <p className="caption">Prompt atlas</p>
            <h2>Timeline Lanes</h2>
          </div>
          <div className="corpusControls">
            <select value={lane} onChange={(event) => setLane(event.target.value)} aria-label="Filter lane">
              <option value="all">All lanes</option>
              {laneOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <select value={kind} onChange={(event) => setKind(event.target.value)} aria-label="Filter kind">
              <option value="all">All kinds</option>
              {kindOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter IDs, lanes, clusters"
              aria-label="Search corpus units"
            />
          </div>
        </div>
        <div className="corpusTimeline" role="table" aria-label="Redacted corpus timeline">
          {filteredUnits.map((unit) => (
            <div className="corpusUnitRow" key={unit.unit_id} role="row">
              <div className="corpusUnitTime" role="cell">
                {dateLabel(unit.event_at)}
              </div>
              <div className="corpusUnitMain" role="cell">
                <strong>{shortId(unit.unit_id)}</strong>
                <span>{unit.kind} / {unit.role} / {unit.source}</span>
                <small>{unit.lane_id} / {shortId(unit.cluster_id)}</small>
              </div>
              <div className="corpusUnitMeta" role="cell">
                <span>{formatNumber(unit.body_words)} words</span>
                <span>{formatNumber(unit.atom_ids.length)} atoms</span>
              </div>
            </div>
          ))}
          {!filteredUnits.length && (
            <div className="corpusEmpty">No units match the current filters.</div>
          )}
        </div>
        {data.truncated_units && (
          <p className="corpusNote">The redacted dashboard is bounded; the private index contains the complete corpus.</p>
        )}
      </section>

      <section className="corpusPanel">
        <div className="corpusPanelHeader">
          <div>
            <p className="caption">Side-by-side</p>
            <h2>Evolution Pairs</h2>
          </div>
          <select
            value={selectedComparison?.comparison_id || ""}
            onChange={(event) => setSelectedComparisonId(event.target.value)}
            aria-label="Select comparison"
          >
            {data.comparisons.map((item) => (
              <option key={item.comparison_id} value={item.comparison_id}>
                {shortId(item.cluster_id)} / {item.unit_count}
              </option>
            ))}
          </select>
        </div>
        {selectedComparison ? (
          <div className="corpusCompare">
            <div>
              <span>First</span>
              <strong>{shortId(selectedComparison.left_unit_id)}</strong>
              <p>{dateLabel(selectedComparison.first_event)} / {leftUnit?.kind || "unit"} / {leftUnit?.lane_id || "lane"}</p>
            </div>
            <div>
              <span>Latest</span>
              <strong>{shortId(selectedComparison.right_unit_id)}</strong>
              <p>{dateLabel(selectedComparison.last_event)} / {rightUnit?.kind || "unit"} / {rightUnit?.lane_id || "lane"}</p>
            </div>
            <p className="corpusNote">Raw bodies are private. Use the private explorer path in the receipt to inspect exact text.</p>
          </div>
        ) : (
          <div className="corpusEmpty">No comparison pairs yet.</div>
        )}
      </section>

      <section className="corpusPanel">
        <p className="caption">Atomic unit ledger</p>
        <h2>Allusions</h2>
        <div className="corpusAtomList">
          {data.allusions.slice(0, 12).map((row) => (
            <div key={row.unit_id}>
              <strong>{shortId(row.unit_id)}</strong>
              <span>explicit {row.explicit_atom_ids.length}</span>
              <span>implied {row.implied_atom_ids.length}</span>
              <span>not-present {row.absent_adjacent_atom_ids.length}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="corpusPanel">
        <p className="caption">August 1</p>
        <h2>No-Unemployment Gate</h2>
        <div className={data.aug1.gate_pass ? "corpusGate pass" : "corpusGate fail"}>
          <strong>{data.aug1.gate_pass ? "TRUE" : "FALSE"}</strong>
          <span>{data.aug1.legs_met}/{data.aug1.legs_total} legs met / {data.aug1.days_left ?? "?"} days left</span>
        </div>
        {data.aug1.next_act && <p className="corpusNote">{data.aug1.next_act}</p>}
      </section>

      <section className="corpusPanel">
        <p className="caption">Inbound magnet</p>
        <h2>Scraper Model</h2>
        <div className="corpusSignalGrid">
          <span>Value repos <strong>{data.inbound.value_repo_count}</strong></span>
          <span>Seeded <strong>{data.inbound.seeded_repo_count}</strong></span>
          <span>Front door <strong>{data.inbound.frontdoor_present ? "ready" : "missing"}</strong></span>
          <span>Scraper <strong>{data.inbound.scraper_model_present ? "model" : "missing"}</strong></span>
          <span>Capture <strong>{data.inbound.capture_contact_configured ? "live" : "off"}</strong></span>
        </div>
      </section>

      <section className="corpusPanel">
        <p className="caption">Receipt</p>
        <h2>Private Surface</h2>
        <dl className="corpusReceipt">
          <dt>Private index</dt>
          <dd>{data.privacy.private_index || "not generated"}</dd>
          <dt>Private explorer</dt>
          <dd>{data.privacy.private_html || "not generated"}</dd>
          <dt>Raw text in this route</dt>
          <dd>{data.privacy.contains_raw_text ? "yes" : "no"}</dd>
        </dl>
      </section>
    </div>
  );
}
