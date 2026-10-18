const data = JSON.parse(document.getElementById("dataset").textContent);
const picker = document.getElementById("picker");
const board = document.getElementById("board");
const search = document.getElementById("search");
function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}
function candidates(session, position) {
  if (position === 0) return "First retained prompt: original opener still requires lineage review";
  return session.annotations?.[position - 1] || "Uncoded: preserve the complete payload";
}
function render() {
  board.replaceChildren();
  const chosen = Array.from(picker.selectedOptions).map(option => Number(option.value));
  document.getElementById("selection").textContent = chosen.length + " captured file sequences selected";
  for (const index of chosen) {
    const session = data.sessions[index];
    const column = node("article");
    const header = node("header");
    header.append(node("h2", session.alias || session.id.slice(0, 8)),
      node("p", session.cwd || "Directory unknown"), node("small", session.id),
      node("p", session.prompts.every(p => p.retained_complete === true) ?
        "All retained bodies marked complete. Logical-session completeness unproven." :
        "Retained-body gaps or unknown completeness: do not assume the opener survived."));
    column.append(header);
    const list = node("ol");
    session.prompts.forEach((prompt, position) => {
      const item = node("li");
      item.append(node("strong", candidates(session, position)),
        node("p", "Native line " + prompt.line + " | body completeness: " + String(prompt.retained_complete), "meta"),
        node("pre", prompt.text));
      if (prompt.media.length) item.append(node("p", "Media descriptors only: " + prompt.media.join(", ") + ". Inspect the original input for visual meaning.", "meta"));
      const replies = node("details");
      replies.append(node("summary", "Recorded replies and actions (" + prompt.finals.length + ")"),
        node("p", "Historical claims, not current verification. Tool calls: " + prompt.tool_calls, "meta"));
      for (const reply of prompt.finals) {
        if (reply.phase_inferred) replies.append(node("p", "Final phase inferred from last captured assistant text.", "meta"));
        replies.append(node("pre", reply.text));
      }
      item.append(replies);
      list.append(item);
    });
    column.append(list);
    board.append(column);
  }
}
function filter() {
  const query = search.value.toLowerCase();
  for (const option of picker.options) {
    const session = data.sessions[Number(option.value)];
    option.hidden = !(session.id + " " + session.cwd + " " + session.prompts.map(prompt => prompt.text).join(" ") + " " + (session.annotations || []).join(" ")).toLowerCase().includes(query);
  }
}
data.sessions.forEach((session, index) => {
  const option = node("option", (session.alias || session.id.slice(0, 8)) + " | " + session.cwd + " | " + session.prompts.length + " prompts");
  option.value = index;
  option.selected = ["S1", "S3", "S8"].includes(session.alias);
  picker.append(option);
});
document.getElementById("compare").addEventListener("click", render);
document.getElementById("all").addEventListener("click", () => {
  for (const option of picker.options) option.selected = !option.hidden;
  render();
});
search.addEventListener("input", filter);
render();
