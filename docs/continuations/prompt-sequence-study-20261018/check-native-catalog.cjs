// Check catalog data and render logic without a browser or any network transport.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const page = fs.readFileSync(process.argv[2], "utf8");
const jsonText = page.match(/<script type="application\/json" id="dataset">([\s\S]*?)<\/script>/)[1];
const actual = JSON.parse(jsonText);
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.handlers = {}; this.value = ""; this.selected = false; this.hidden = false; this.textContent = ""; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  get options() { return this.children; }
  get selectedOptions() { return this.children.filter(child => child.selected); }
}
const ids = Object.fromEntries(["dataset", "picker", "board", "search", "selection", "compare", "all"].map(id => [id, new Element(id)]));
ids.dataset.textContent = jsonText;
const document = { getElementById: id => ids[id], createElement: tag => new Element(tag) };
const runtime = page.match(/<script>([\s\S]*?)<\/script>/)[1];
vm.runInNewContext(runtime, { document }, { timeout: 5000 });
assert.equal(ids.board.children.length, 3);
const walk = item => [item, ...item.children.flatMap(walk)];
assert.equal(walk(ids.board).filter(item => item.tagName === "li").length, 14);
ids.all.handlers.click();
assert.equal(ids.board.children.length, actual.sessions.length);
assert.equal(walk(ids.board).filter(item => item.tagName === "li").length, actual.sessions.reduce((sum, session) => sum + session.prompts.length, 0));
const renderedTexts = new Set(walk(ids.board).filter(item => item.tagName === "pre").map(item => item.textContent));
for (const session of actual.sessions) for (const prompt of session.prompts) assert.ok(renderedTexts.has(prompt.text));
assert.equal(page.includes('src="http'), false);


assert.ok(walk(ids.board).some(item => item.textContent === "Response attribution: shared-native-turn"));
assert.ok(walk(ids.board).some(item => typeof item.textContent === "string" && item.textContent.startsWith("Derived context frames kept separately")));

const current = page.match(/<details id="current-vocabulary">([\s\S]*?)<\/details>/);
assert.ok(current, "the comparison must display its current vocabulary");
const currentNames = Array.from(current[1].matchAll(/<code>(\/[^<]+)<\/code>/g), item => item[1]).sort();
const expectedNames = JSON.parse(fs.readFileSync(__dirname + "/vocabulary-v5.json", "utf8")).commands.map(item => item.name).sort();
assert.deepEqual(currentNames, expectedNames, "displayed operation names must match the current operator proposal");
const managedColumn = ids.board.children.find(column => walk(column).some(item => item.tagName === "h2" && item.textContent === "U3"));
assert.ok(managedColumn, "the managed-input source must be identifiable");
const managedRows = walk(managedColumn).filter(item => item.tagName === "li");
assert.equal(managedRows.length, 10);
const managedLabels = managedRows.map(row => walk(row).find(item => item.tagName === "strong").textContent);
assert.equal(managedLabels.filter(text => text.startsWith("Managed recovery input;")).length, 6);
assert.ok(managedLabels.slice(4, 10).every(text => text.startsWith("Managed recovery input;")));
console.log(JSON.stringify({ columns: ids.board.children.length, originalPromptsPreserved: actual.sessions.reduce((n,s) => n+s.prompts.length,0), currentOperations: currentNames.length, managedInputs: 6, browserVisualInspection: "not performed" }));
