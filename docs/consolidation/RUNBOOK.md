# GitHub consolidation: personal-first execution

**Direction approved:** September 24, 2026. **Work owner:** [Limen #2721](https://github.com/4444J99/limen/issues/2721).

`4444J99` is the destination, never a source. `organvm`, the seven organ organizations,
`meta-organvm`, and `a-organvm` are migration sources. Preserve ORGANVM membership in
the existing registry, `seed.yaml`, and topics. Repository ownership is not organ
membership, maturity, visibility, or merge authority. No new repository or scheduler
is needed. Launch or revenue does not automatically require a product organization.

This replaces the June 28 transfer-into-`organvm` packet. The
[historical packet remains available at its immutable revision](https://github.com/4444J99/limen/blob/b0ca0d6783cee15911c1135c3ac00d3889a529f2/docs/consolidation/RUNBOOK.md).
Historical commands in `SCOPE-AND-APP.md`, `COLLISION-RENAMES.md`, and earlier dossiers
are evidence, not authority to reverse this direction. **Do not run the legacy
`scripts/rewrite-owners.py --apply` into `organvm`. Do not edit the broker-owned
`tasks.yaml` projection.** Reconcile each actual location through its existing owner.

## Boundaries

- Authorization is already given. Preservation evidence and demonstrated tool capability
  remain necessary; they are not another permission request to the user.
- Never delete an organization or repository, change visibility, raise a budget, remove a
  hold label, bypass protection, or install broadly privileged Apps as part of a transfer.
- Inspect private destination access and Free-plan feature loss before transfer. Private
  repository names, integration inventories, and credentials must not enter a public
  receipt or index. Topic names themselves are public, including on private repositories.
- Keep logical organs, product groupings, existing topics, history, and current archive
  state. A source-sphere topic records former hosting; it does not classify the logical organ.
- Profiles (`.github`), Pages, and name collisions remain explicit per-repository holds.
  Do not rename or move those automatically. No single held repository blocks an explicitly
  partial, reviewed batch of other repositories.

## Execution environment

Use the existing owner-authenticated GitHub CLI under `4444J99` in an already-authorized
administration-capable environment. Keep credentials in their existing credential authority;
do not introduce another token store or paste tokens into issues, source, or chat.

The Chat connection inspected for #2721 supports repository code and PR changes, but exposes
no transfer, topic-update, organization-archive, billing, or organization-asset administration
action. Its container has no `gh` executable or authenticated GitHub CLI session. This is a
capability observation for that session, not a claim that GitHub reserves transfers for humans.
The REST API supports repository transfers with the required administration permissions.

## 1. Inventory without effects

```bash
python3 scripts/consolidate-github.py --receipt /private/path/consolidation-plan.json
```

The script paginates the ten source organizations and the authenticated owner's repositories,
including credential-visible private repositories. It checks source and destination name
collisions together. An error, malformed response, duplicate identity, or pagination limit
is a failure, never an empty organization. Full pagination does not prove that a restricted
credential can see every private repository; that coverage remains separately assessed.

Console output is count-only. The JSON receipt is atomically written with mode `0600` and
includes repository identities, visibility, topics, and holds. Keep it outside public working
trees or in an existing private evidence location. A dry-run plan is not an asset audit.

## 2. Complete the preservation preflight

The executing agent uses available administration reads to inspect each candidate; do not
ask the user to fill in routine engineering facts. The private evidence must cover:

- Destination App exposure and any credential or secret/variable inheritance changes.
- Collaborator roles, issue assignees and issue types that need preservation; protection
  and ruleset behavior at the personal account's actual plan level.
- Package/container ownership and consumer references, deployments, Pages/custom domains,
  inherited community files, and reusable workflow dependencies.
- Stable repository identity, current owner, visibility, archive state, branch and collision
  resolution. Preserve pre-transfer metadata and recheck any drift before applying.

Record accepted technical preflight rows in the same private evidence area:

```json
{
  "schema": "limen.github_consolidation_preflight.v1",
  "target": "4444J99",
  "repositories": [
    {
      "id": 123,
      "full_name": "organvm/example",
      "destination": "4444J99/example",
      "visibility": "public",
      "archived": false,
      "default_branch": "main",
      "preservation_checked": false,
      "evidence_ref": ""
    }
  ]
}
```

This is a deliberately **unapproved synthetic example**, not a live repository. Populate rows
from observations. Set `preservation_checked` true only after the technical checks above pass,
and reference the private evidence. The record neither creates authority nor proves a transfer.
Do not auto-certify it from a topic, a successful GET, or the existence of user authorization.
Unreviewed and mismatched rows remain held. Reassess when relevant state or access changes.

## 3. Apply the reviewed batch

```bash
python3 scripts/consolidate-github.py \
  --apply --allow-partial \
  --preflight /private/path/consolidation-preflight.json \
  --receipt /private/path/consolidation-apply.json
```

This uses native transfers and does not create replacement repositories. Before each request,
it verifies the stable repository ID, source owner, visibility, archive state, default branch,
and Pages state. It writes a private checkpoint before an effect. It verifies ownership by
stable ID after the asynchronous request, preserves existing and freshly observed topics, and
never unarchives a repository just to add a topic. Archived repositories retain their existing
topics and source provenance in the receipt.

A request can remain `accepted_unverified` while GitHub processes it or awaits acceptance.
Do not call it moved or blindly resubmit it. An uncertain/failed effect stops the batch for
reconciliation, and the receipt retains the last observed state. Exit `1` means failure,
`2` means held/incomplete work, and `3` means accepted but unverified. Exit `0` in apply mode
means the selected repository-transfer operations verified; it does **not** establish
integration health, billing resolution, or organization retirement.

## 4. Verify and reconcile integrations

For each verified transfer, update the existing registry and seed's current hosting fields
without moving the record to a different logical organ. Bind identity to repository ID;
owner/name is a location. Update active remotes, Actions/reusable-workflow references,
deployments, packages, and approved agent installations. Preserve historical receipts and
old URLs as historical evidence rather than rewriting history.

Run required checks on the accepted source and verify deployments and access at the destination.
Only then mark integration acceptance. Do not remove an old owner from operational discovery
while it still hosts unreconciled active work. Do not treat an independent lifecycle hold or
failing required check as resolved by changing repository ownership.

## 5. Retire organizations without deleting them

Preserve organization-owned projects, audit/billing records, shared configuration, package
registries, GitHub App registrations, and any retained profile or Pages assets. Verify that
private visibility coverage is complete; a repository search is not this audit. Reconcile
separately billed services and the actual account disposition without increasing spending.

After the affected work is transferred or explicitly retained and made non-operational, update
the old profile with the destination and archive the organization on Free. GitHub's organization
archive is a separate operation that makes remaining repositories read-only; `gh repo archive`
is not an organization archive. The transfer script deliberately performs neither operation.
Archive preservation-only exceptions only after their dependencies are verified. Do not delete
the organizations, release their names, or claim the payment incident resolved without evidence.

## Verification and sources

```bash
python3 -m unittest discover -s tests -p test_consolidate_github.py -v
```

These are offline logic regressions, not proof of an authenticated transfer. Whole-workstream
acceptance requires the actual transfer, integration and retirement receipts in #2721.

- [GitHub repository transfer behavior](https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository)
- [Repository transfer API](https://docs.github.com/en/rest/repos/repos#transfer-a-repository)
- [Organization archive behavior](https://docs.github.com/en/organizations/managing-organization-settings/archiving-an-organization)
- [Repository topics and privacy](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics)
