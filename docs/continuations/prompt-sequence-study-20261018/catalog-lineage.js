// Native lineage notes do not change the embedded captured prompts.
const lineageData = __LINEAGE_DATA__;
const lineageRoot = document.getElementById("lineage");
if (!lineageRoot) throw new Error("The lineage display is absent");
const lineageParents = new Map();
for (const row of lineageData.rows) {
  if (!row.parent_id) continue;
  const parent = data.sessions.find(session => session.id === row.parent_id);
  if (!parent) continue;
  if (!parent.parentLineage) {
    parent.parentLineage = { alias: row.parent_alias, views: [] };
    if (!parent.alias) parent.alias = row.parent_alias;
  }
  if (!parent.parentLineage.views.includes(row.alias)) parent.parentLineage.views.push(row.alias);
  lineageParents.set(row.parent_id, parent);
}
function lineageNode(tag, text) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  return element;
}
const lineageParentCount = new Set(lineageData.rows.filter(row => row.parent_id).map(row => row.parent_id)).size;
lineageRoot.append(
  lineageNode("p", lineageData.rows.length + " checked native views; " +
    lineageData.rows.filter(row => row.parent_id).length + " declared forks. File columns cover " +
    lineageParents.size + " of " + lineageParentCount + " declared parents."),
  lineageNode("p", "Search a fork alias to find its captured parent column when available. Fork-only payloads are not copied into these file columns. Multiple reader positions remain unresolved input attribution.")
);
const lineageTable = lineageNode("table");
const lineageHead = lineageNode("tr");
for (const label of ["View", "Relation", "Parent context", "Local source line", "Reader input positions", "Evidence"]) {
  lineageHead.append(lineageNode("th", label));
}
lineageTable.append(lineageHead);
for (const row of lineageData.rows) {
  const item = lineageNode("tr");
  const parent = row.parent_id ? data.sessions.find(session => session.id === row.parent_id) : null;
  const evidence = row.local_line === null ? "Prefix limit reached" :
    row.attribution === "shared_turn_unresolved" ? "Shared turn: input unresolved" :
    row.body_match ? "Exact local opener" : "Native turn binding";
  const values = [
    row.alias,
    row.parent_id ? "Declared fork" : "Direct candidate",
    row.parent_id ? row.parent_alias + (parent ? " (in file columns)" : " (outside file columns)") : "—",
    row.local_line === null ? "Unresolved" : String(row.local_line),
    row.reader_positions.length ? row.reader_positions.join(", ") : "Unresolved",
    evidence
  ];
  for (const value of values) item.append(lineageNode("td", value));
  lineageTable.append(item);
}
lineageRoot.append(lineageTable,
  lineageNode("p", "M24 / R01: 7 context inputs + 26 local inputs. The first local opener matches reader input 8 exactly; the parent capture's first two bodies retain completeness gaps."),
  lineageNode("p", "These are retained-source relationships, not independent original sessions or proof of complete pre-retention history.")
);
