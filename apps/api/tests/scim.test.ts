import { test } from "node:test";
import assert from "node:assert";
import { SCIMDirectoryService } from "../scim.ts";

test("SCIM User provisioning and query lifecycle", () => {
  const service = new SCIMDirectoryService();

  const user = service.createUser({
    userName: "alice@example.com",
    externalId: "ext-101",
    name: { formatted: "Alice Smith" },
    active: true,
  });

  assert.strictEqual(user.userName, "alice@example.com");
  assert.strictEqual(user.active, true);

  const listRes = service.getUsers('userName eq "alice@example.com"');
  assert.strictEqual(listRes.totalResults, 1);
  assert.strictEqual(listRes.Resources[0].id, user.id);

  // Deactivate user
  service.deactivateUser(user.id);
  const fetched = service.getUserById(user.id);
  assert.strictEqual(fetched?.active, false);
});

test("SCIM Group management", () => {
  const service = new SCIMDirectoryService();

  const group = service.createGroup({
    displayName: "Engineering",
    members: [{ value: "usr-01", display: "Alice Smith" }],
  });

  assert.strictEqual(group.displayName, "Engineering");
  assert.strictEqual(group.members?.length, 1);

  const groupsRes = service.getGroups();
  assert.strictEqual(groupsRes.totalResults, 2); // Default admin + Engineering
});
