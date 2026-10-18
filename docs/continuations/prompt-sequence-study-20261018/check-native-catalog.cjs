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
vm.runInNewContext(fs.readFileSync(__dirname + "/native-catalog.js", "utf8"), { document });
assert.equal(ids.board.children.length, 3);
const walk = item => [item, ...item.children.flatMap(walk)];
assert.equal(walk(ids.board).filter(item => item.tagName === "li").length, 14);
ids.all.handlers.click();
assert.equal(ids.board.children.length, actual.sessions.length);
assert.equal(walk(ids.board).filter(item => item.tagName === "li").length, actual.sessions.reduce((sum, session) => sum + session.prompts.length, 0));
const renderedTexts = new Set(walk(ids.board).filter(item => item.tagName === "pre").map(item => item.textContent));
for (const session of actual.sessions) for (const prompt of session.prompts) assert.ok(renderedTexts.has(prompt.text));
assert.equal(page.includes('src="http'), false);
console.log(JSON.stringify({ columns: ids.board.children.length, originalPromptsPreserved: actual.sessions.reduce((n,s) => n+s.prompts.length,0), browserVisualInspection: "not performed" }));
