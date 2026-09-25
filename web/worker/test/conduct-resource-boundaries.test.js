import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { conflictingKeys, normalizeResourceKey, parseResource, resourcesOverlap, sortedClaims } from "../src/conduct/resources.js";

const vectors = JSON.parse(readFileSync(new URL("../../../spec/contracts/conduct/resource-overlap-vectors.json", import.meta.url), "utf8"));
for (const vector of vectors) {
  test(`shared resource boundary: ${vector.id}`, () => {
    assert.equal(resourcesOverlap(vector.left, vector.right), vector.overlap);
    assert.equal(resourcesOverlap(vector.right, vector.left), vector.overlap);
    assert.equal(conflictingKeys([vector.left], [vector.right]).length > 0, vector.overlap);
  });
}

test("root aliases stay typed and deduplicate to the strongest claim", () => {
  const keys = ["path/Example/Repo/main", "path/Example/Repo/main/", "path/Example/Repo/main/.", "path/Example/Repo/main/src/.."];
  for (const key of keys) {
    const canonical = normalizeResourceKey(key);
    assert.equal(canonical, "path/example/repo/main");
    assert.equal(normalizeResourceKey(canonical), canonical);
    assert.equal(parseResource(canonical).kind, "path");
    assert.equal(parseResource(canonical).prefix, "/");
  }
  assert.deepEqual(sortedClaims([
    ...keys.map(key => ({ key, mode: "shared" })),
    { key: keys[0], mode: "exclusive" },
  ]), [{ schema_version: "limen.resource_claim.v1", key: "path/example/repo/main", mode: "exclusive" }]);
});

test("one thousand repository roots remain independent", () => {
  const held = Array.from({ length: 1000 }, (_, index) => ({ key: `path/example/repo-${index}/main`, mode: "exclusive" }));
  assert.deepEqual(conflictingKeys([{ key: "path/example/repo-499/main/src/service.py", mode: "exclusive" }], held), [
    ["path/example/repo-499/main/src/service.py", "path/example/repo-499/main"],
  ]);
});
