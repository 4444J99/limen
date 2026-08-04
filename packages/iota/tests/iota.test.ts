import { strict as assert } from "node:assert";
import { test } from "node:test";
import { IotaDomainStore } from "../src/index.ts";
import type { IotaProvenance } from "../src/index.ts";

const basePartition = "partition-01";

function fixedNow(start = "2026-01-01T00:00:00.000Z"): () => string {
  let current = Date.parse(start);
  return () => {
    const result = new Date(current).toISOString();
    current += 1_000;
    return result;
  };
}

function person(actorId = "operator-01"): IotaProvenance {
  return {
    actorId,
    actorType: "operator",
  };
}

function extractIdentityId(store: IotaDomainStore, proposalId: string): string {
  const proposal = store.proposalById(proposalId);
  if (!proposal || !proposal.effect?.createdIdentityId) {
    throw new Error(`proposal ${proposalId} missing createdIdentityId`);
  }
  return proposal.effect.createdIdentityId;
}

test("IOTA-01 creates identities and relationships through explicit proposals", () => {
  const store = new IotaDomainStore({ now: fixedNow() });
  const keeper = store.approveProposal(
    store.proposeIdentity({
      partitionId: basePartition,
      kind: "person",
      canonicalName: "Alice Operator",
      aliases: ["alice", "a.operator"],
      provenance: person("alice"),
    }).proposalId,
  );
  const partner = store.approveProposal(
    store.proposeIdentity({
      partitionId: basePartition,
      kind: "organization",
      canonicalName: "Acme Org",
      provenance: person("planner"),
    }).proposalId,
  );
  const ownerId = extractIdentityId(store, keeper.proposalId);
  const orgId = extractIdentityId(store, partner.proposalId);

  const proposal = store.proposeRelationship({
    partitionId: basePartition,
    sourceIdentityId: ownerId,
    targetIdentityId: orgId,
    relationshipType: "member-of",
    provenance: person("planner"),
  });

  const relationshipProposal = store.approveProposal(proposal.proposalId);
  assert.strictEqual(relationshipProposal.status, "approved");
  const [relationship] = store.getRelationshipsForIdentity(ownerId);
  assert.strictEqual(relationship.sourceIdentityId, ownerId);
  assert.strictEqual(relationship.targetIdentityId, orgId);

  const engagementProposal = store.approveProposal(
    store.proposeEngagement({
      partitionId: basePartition,
      relationshipId: relationship.relationshipId,
      title: "Quarterly Planning",
      provenance: person("planner"),
    }).proposalId,
  );
  assert.strictEqual(engagementProposal.status, "approved");
  assert.strictEqual(engagementProposal.effect?.kind, "engagement.create");
  assert.strictEqual(store.getEngagementsForRelationship(relationship.relationshipId).length, 1);
});

test("IOTA-01 forbids proposal leakage across partitions", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-02-01T00:00:00.000Z") });
  const partitionOnePerson = extractIdentityId(
    store,
    store.approveProposal(
      store.proposeIdentity({
        partitionId: "partition-01",
        kind: "person",
        canonicalName: "Alice",
        provenance: person("alice"),
      }).proposalId,
    ).proposalId,
  );
  const partitionTwoPerson = extractIdentityId(
    store,
    store.approveProposal(
      store.proposeIdentity({
        partitionId: "partition-02",
        kind: "person",
        canonicalName: "Bob",
        provenance: person("bob"),
      }).proposalId,
    ).proposalId,
  );

  assert.throws(() => {
    store.proposeRelationship({
      partitionId: "partition-01",
      sourceIdentityId: partitionOnePerson,
      targetIdentityId: partitionTwoPerson,
      relationshipType: "peer",
      provenance: person("planner"),
    });
  }, /partition leak|cross-partition/);

  assert.throws(() => {
    store.proposeIdentityMerge({
      partitionId: "partition-01",
      keptIdentityId: partitionOnePerson,
      mergedIdentityId: partitionTwoPerson,
      provenance: person("planner"),
    });
  }, /partition leak|cross-partition/);
});

test("IOTA-01 tracks reversible identity create/merge effects", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-03-01T00:00:00.000Z") });

  const first = store.approveProposal(
    store.proposeIdentity({
      partitionId: basePartition,
      kind: "person",
      canonicalName: "Primary",
      provenance: person("planner"),
    }).proposalId,
  );
  const second = store.approveProposal(
    store.proposeIdentity({
      partitionId: basePartition,
      kind: "person",
      canonicalName: "Secondary",
      provenance: person("planner"),
    }).proposalId,
  );
  const primaryId = extractIdentityId(store, first.proposalId);
  const secondaryId = extractIdentityId(store, second.proposalId);

  const proposal = store.approveProposal(
    store.proposeIdentityMerge({
      partitionId: basePartition,
      keptIdentityId: primaryId,
      mergedIdentityId: secondaryId,
      provenance: person("planner"),
    }).proposalId,
  );

  const merged = store.getIdentity(secondaryId);
  assert.strictEqual(merged?.active, false);
  assert.strictEqual(merged?.mergedInto, primaryId);

  const reverted = store.revertProposal(proposal.proposalId);
  assert.strictEqual(reverted.status, "reverted");
  const restored = store.getIdentity(secondaryId);
  assert.ok(restored);
  assert.strictEqual(restored?.active, true);
});

test("IOTA-01 supports immediate and reversible engagement state transitions", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-04-01T00:00:00.000Z") });
  const keeper = extractIdentityId(
    store,
    store.approveProposal(
      store.proposeIdentity({
        partitionId: basePartition,
        kind: "person",
        canonicalName: "Planner",
        provenance: person("planner"),
      }).proposalId,
    ).proposalId,
  );
  const sponsor = extractIdentityId(
    store,
    store.approveProposal(
      store.proposeIdentity({
        partitionId: basePartition,
        kind: "organization",
        canonicalName: "Partner",
        provenance: person("planner"),
      }).proposalId,
    ).proposalId,
  );
  const relationship = store.approveProposal(
    store.proposeRelationship({
      partitionId: basePartition,
      sourceIdentityId: keeper,
      targetIdentityId: sponsor,
      relationshipType: "sponsors",
      provenance: person("planner"),
    }).proposalId,
  );

  const engagement = store.approveProposal(
    store.proposeEngagement({
      partitionId: basePartition,
      relationshipId: relationship.effect?.createdRelationshipId || "",
      title: "Quarterly update",
      provenance: person("planner"),
    }).proposalId,
  );
  assert.strictEqual(engagement.effect?.createdEngagementId ? true : false, true);

  const engagementId = engagement.effect?.createdEngagementId || "";
  const activate = store.setEngagementState(engagementId, "active", person("planner"));
  assert.strictEqual(activate.status, "approved");
  const reverted = store.revertProposal(activate.proposalId);
  assert.strictEqual(reverted.status, "reverted");

  const engagementTimeline = store.getEngagementsForRelationship(relationship.effect?.createdRelationshipId || "");
  assert.strictEqual(engagementTimeline[0]?.state, "proposed");
});

test("IOTA-01 emits partition-scoped timeline events and windowed readback", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-05-01T00:00:00.000Z") });

  const one = extractIdentityId(
    store,
    store.approveProposal(
      store.proposeIdentity({
        partitionId: "partition-a",
        kind: "person",
        canonicalName: "Alice",
        provenance: person("operator"),
      }).proposalId,
    ).proposalId,
  );
  const two = extractIdentityId(
    store,
    store.approveProposal(
      store.proposeIdentity({
        partitionId: "partition-a",
        kind: "person",
        canonicalName: "Bob",
        provenance: person("operator"),
      }).proposalId,
    ).proposalId,
  );

  const relation = store.approveProposal(
    store.proposeRelationship({
      partitionId: "partition-a",
      sourceIdentityId: one,
      targetIdentityId: two,
      relationshipType: "peer",
      provenance: person("operator"),
    }).proposalId,
  );
  assert.ok(relation.effect);

  const scopedTimeline = store.getTimeline("partition-a", { limit: 2 });
  const allTimeline = store.getTimeline("partition-a");
  assert.strictEqual(scopedTimeline.partitionId, "partition-a");
  assert.strictEqual(scopedTimeline.events.length, 2);
  assert.ok(allTimeline.events.every((entry) => entry.partitionId === "partition-a"));
  assert.strictEqual(
    scopedTimeline.events[0].occurredAt.localeCompare(scopedTimeline.events[1].occurredAt) < 0,
    true,
  );

  const before = store.getTimeline("partition-a", {
    before: "2026-05-01T00:00:01.500Z",
  });
  assert.ok(before.events.length < allTimeline.events.length);
});

test("IOTA-01 surfaces partition-filtered proposal queries", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-06-01T00:00:00.000Z") });
  store.approveProposal(
    store.proposeIdentity({
      partitionId: "partition-a",
      kind: "person",
      canonicalName: "Carol",
      provenance: person("operator"),
    }).proposalId,
  );
  store.approveProposal(
    store.proposeIdentity({
      partitionId: "partition-b",
      kind: "person",
      canonicalName: "Dora",
      provenance: person("operator"),
    }).proposalId,
  );
  const proposalsA = store.listProposals("partition-a");
  const proposalsB = store.listProposals("partition-b");

  assert.strictEqual(
    proposalsA.every((entry) => entry.partitionId === "partition-a"),
    true,
  );
  assert.strictEqual(
    proposalsB.every((entry) => entry.partitionId === "partition-b"),
    true,
  );
});

test("IOTA-02 creates commitments with stateful lifecycle and waits semantics", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-07-01T00:00:00.000Z") });
  const first = store.proposeCommitment({
    partitionId: basePartition,
    title: "Draft notes",
    assigneeId: "operator-a",
    dueAt: "2026-07-05T00:00:00.000Z",
    provenance: person("planner"),
  });
  const firstApproved = store.approveProposal(first.proposalId);
  const firstId = firstApproved.effect?.createdCommitmentId || "";

  const second = store.proposeCommitmentTransition({
    commitmentId: firstId,
    nextState: "active",
    rationale: "ready to start",
    waitingOn: [],
    provenance: person("planner"),
  });
  assert.strictEqual(second.effect?.commitmentStateTo, "active");
  assert.strictEqual(store.getCommitment(firstId).state, "active");

  const blocked = store.proposeCommitmentTransition({
    commitmentId: firstId,
    nextState: "blocked",
    rationale: "external dependency",
    provenance: person("planner"),
  });
  assert.strictEqual(blocked.effect?.commitmentStateTo, "blocked");
  assert.strictEqual(store.getCommitment(firstId).state, "blocked");

  const reopened = store.proposeCommitmentTransition({
    commitmentId: firstId,
    nextState: "reopened",
    rationale: "dependency cleared",
    provenance: person("planner"),
  });
  assert.strictEqual(store.getCommitment(firstId).state, "reopened");
  assert.strictEqual(reopened.effect?.commitmentStateFrom, "blocked");
  assert.strictEqual(store.getCommitment(firstId).reopenedCount, 1);

  const complete = store.proposeCommitmentTransition({
    commitmentId: firstId,
    nextState: "complete",
    rationale: "done",
    provenance: person("planner"),
  });
  assert.strictEqual(complete.effect?.commitmentStateTo, "complete");

  assert.throws(() => {
    store.proposeCommitmentTransition({
      commitmentId: firstId,
      nextState: "active",
      rationale: "bad terminal transition",
      provenance: person("planner"),
    });
  }, /invalid commitment transition/);
});

test("IOTA-02 enforces partition-safe wait dependencies and completion flags", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-07-10T00:00:00.000Z") });
  store.approveProposal(
    store.proposeIdentity({
      partitionId: basePartition,
      kind: "person",
      canonicalName: "Owner",
      provenance: person("planner"),
    }).proposalId,
  );
  store.approveProposal(
    store.proposeIdentity({
      partitionId: "other-partition",
      kind: "person",
      canonicalName: "Other",
      provenance: person("planner"),
    }).proposalId,
  );

  const waitingOne = store.approveProposal(
    store.proposeCommitment({
      partitionId: basePartition,
      title: "Dependency",
      assigneeId: "operator-a",
      dueAt: "2026-07-11T00:00:00.000Z",
      provenance: person("planner"),
    }).proposalId,
  );

  const dependent = store.proposeCommitment({
    partitionId: basePartition,
    title: "Waiting task",
    assigneeId: "operator-b",
    dueAt: "2026-07-12T00:00:00.000Z",
    waitingOn: ["non-existing-commitment"],
    provenance: person("planner"),
  });
  assert.throws(
    () => store.approveProposal(dependent.proposalId),
    /missing waiting task|waiting task/,
  );

  const otherPartitionCommit = store.approveProposal(
    store.proposeCommitment({
      partitionId: "other-partition",
      title: "Cross partition wait",
      assigneeId: "operator-c",
      dueAt: "2026-07-11T00:00:00.000Z",
      provenance: person("planner"),
    }).proposalId,
  );
  const crossWait = store.proposeCommitment({
    partitionId: basePartition,
    title: "Cross partition dependency",
    assigneeId: "operator-a",
    dueAt: "2026-07-12T00:00:00.000Z",
    waitingOn: [otherPartitionCommit.effect?.createdCommitmentId || ""],
    provenance: person("planner"),
  });
  assert.throws(() => store.approveProposal(crossWait.proposalId), /partition leak|waiting task cross-partition/);

  const dependentCommitment = store.approveProposal(
    store.proposeCommitment({
      partitionId: basePartition,
      title: "Waiting task",
      assigneeId: "operator-b",
      dueAt: "2026-07-12T00:00:00.000Z",
      waitingOn: [waitingOne.effect?.createdCommitmentId || ""],
      provenance: person("planner"),
    }).proposalId,
  );

  const dependentId = dependentCommitment.effect?.createdCommitmentId || "";
  assert.strictEqual(store.getCommitment(dependentId).waitingOn[0], waitingOne.effect?.createdCommitmentId);
  assert.strictEqual(store.listWaitingCommitments(basePartition).length >= 1, true);
  assert.ok(waitingOne.effect?.createdCommitmentId);
});

test("IOTA-02 derives overdue, stale, at-risk, and next-action views", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-07-20T00:00:00.000Z") });
  const overdue = store.approveProposal(
    store.proposeCommitment({
      partitionId: basePartition,
      title: "Overdue",
      assigneeId: "operator-a",
      dueAt: "2026-07-18T00:00:00.000Z",
      riskLevel: "medium",
      provenance: person("planner"),
    }).proposalId,
  );
  const staleCommit = store.approveProposal(
    store.proposeCommitment({
      partitionId: basePartition,
      title: "Stale",
      assigneeId: "operator-a",
      dueAt: "2026-07-25T00:00:00.000Z",
      riskLevel: "low",
      provenance: person("planner"),
    }).proposalId,
  );
  const atRisk = store.approveProposal(
    store.proposeCommitment({
      partitionId: basePartition,
      title: "At Risk",
      assigneeId: "operator-b",
      dueAt: "2026-07-20T02:00:00.000Z",
      riskLevel: "high",
      provenance: person("planner"),
    }).proposalId,
  );

  const overdueId = overdue.effect?.createdCommitmentId;
  const staleId = staleCommit.effect?.createdCommitmentId;
  const atRiskId = atRisk.effect?.createdCommitmentId;

  assert.ok(overdueId);
  assert.ok(staleId);
  assert.ok(atRiskId);

  const overdueItems = store.listOverdueCommitments(basePartition);
  assert.strictEqual(overdueItems.length >= 1, true);
  assert.strictEqual(
    overdueItems.some((item) => item.commitmentId === overdueId),
    true,
  );

  const staleItems = store.listStaleCommitments(basePartition, "2026-07-24T00:00:00.000Z", 1_000);
  assert.strictEqual(staleItems.some((item) => item.commitmentId === staleId), true);

  const atRiskItems = store.listAtRiskCommitments(basePartition, "2026-07-20T01:00:00.000Z");
  assert.strictEqual(atRiskItems.some((item) => item.commitmentId === atRiskId), true);

  const nextActions = store.listNextActions(basePartition);
  assert.ok(nextActions.length >= 3);
});

test("IOTA-02 supports milestones, review queues, and risk records", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-07-30T00:00:00.000Z") });
  const milestone = store.approveProposal(
    store.proposeMilestone({
      partitionId: basePartition,
      title: "Q3 milestones",
      dueAt: "2026-09-01T00:00:00.000Z",
      provenance: person("planner"),
    }).proposalId,
  );
  const commitment = store.approveProposal(
    store.proposeCommitment({
      partitionId: basePartition,
      title: "Create timeline",
      assigneeId: "planner",
      dueAt: "2026-08-01T00:00:00.000Z",
      milestoneId: milestone.effect?.createdMilestoneId,
      provenance: person("planner"),
    }).proposalId,
  );

  const milestoneId = milestone.effect?.createdMilestoneId || "";
  const commitmentId = commitment.effect?.createdCommitmentId || "";
  const milestoneAfter = store.getMilestone(milestoneId);
  assert.strictEqual(milestoneAfter.commitmentIds.includes(commitmentId), true);

  const risk = store.recordRisk({
    partitionId: basePartition,
    subjectType: "commitment",
    subjectId: commitmentId,
    level: "high",
    rationale: "dependency risk",
    provenance: person("planner"),
  });
  assert.strictEqual(risk.effect?.createdRiskId ? true : false, true);

  const queue = store.listReviewQueue(basePartition);
  assert.ok(queue.length >= 1);
  const updated = store.resolveReview(queue[0].reviewId, "resolved", "accepted", person("risk-owner"));
  assert.strictEqual(updated.status, "resolved");
  assert.strictEqual(updated.resolution, "accepted");

  const completedMilestone = store.proposeMilestoneTransition({
    milestoneId,
    nextState: "complete",
    rationale: "all commitments done",
    provenance: person("planner"),
  });
  assert.strictEqual(completedMilestone.effect?.milestoneStateTo, "complete");
  assert.strictEqual(store.getMilestone(milestoneId).state, "complete");

  const reviewWithBlocked = store.proposeCommitmentTransition({
    commitmentId,
    nextState: "blocked",
    rationale: "awaiting review",
    provenance: person("planner"),
  });
  assert.strictEqual(reviewWithBlocked.effect?.reviewQueueId ? true : false, true);
});

test("IOTA-03 builds meeting briefs and propagates actions to linked commitments", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-08-01T00:00:00.000Z") });
  const meeting = store.proposeMeeting({
    partitionId: basePartition,
    title: "Risk review council",
      scheduledAt: "2026-07-31T00:00:00.000Z",
    participants: ["planner", "lead"],
    agenda: ["status", "decisions"],
    provenance: person("planner"),
  });
  const meetingId = meeting.effect?.createdMeetingId || "";
  assert.ok(meetingId);

  const decision = store.recordDecision({
    partitionId: basePartition,
    meetingId,
    title: "Adopt risk register format",
    rationale: "Need consistency for external audits",
    alternatives: [
      { option: "Adopt standard schema", rationale: "Predictable interpretation" },
      { option: "Keep custom format", rationale: "Lower short-term effort" },
    ],
    selectedAlternativeIndex: 0,
    participants: ["planner", "lead"],
    evidence: ["external audit prep", "operational handbook draft"],
    actions: [
      {
        title: "Draft schema",
        assigneeId: "planner",
        dueAt: "2026-08-12T00:00:00.000Z",
      },
      {
        title: "Collect sample notes",
        assigneeId: "lead",
        dueAt: "2026-08-13T00:00:00.000Z",
      },
    ],
    provenance: person("planner"),
  });

  const decisionId = decision.effect?.createdDecisionId || "";
  assert.ok(decisionId);
  assert.strictEqual(decision.status, "approved");
  assert.strictEqual(
    Number(decision.effect?.createdCommitmentIds?.length || 0),
    2,
  );

  const brief = store.buildMeetingBrief(meetingId);
  assert.strictEqual(brief.meeting.meetingId, meetingId);
  assert.strictEqual(brief.decisions[0]?.decisionId, decisionId);
  assert.strictEqual(brief.actionCommitments.length, 2);
  assert.strictEqual(brief.openActionCommitments.length, 2);
  assert.ok(brief.timeline.some((event) => event.eventType === "decision.recorded"));

  const meetingDecision = store.getDecision(decisionId);
  assert.deepStrictEqual(meetingDecision.sourceCommitmentIds.sort(), brief.actionCommitments.map((entry) => entry.commitmentId).sort());
  assert.strictEqual(store.getDecisionActions(decisionId).length, 2);
  assert.deepStrictEqual(store.getDecisionActions(decisionId).map((entry) => entry.sourceDecisionIds[0]), [decisionId, decisionId]);
  const note = store.addMeetingNote({
    partitionId: basePartition,
    meetingId,
    authorId: "planner",
    body: "Action items approved and linked",
    provenance: person("planner"),
  });
  assert.ok(note.noteId);
  const meetingWithNote = store.getMeeting(meetingId);
  assert.strictEqual(meetingWithNote.noteIds.length, 1);
});

test("IOTA-03 supports decision supersession and restores prior state on request", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-08-02T00:00:00.000Z") });
  const meeting = store.proposeMeeting({
    partitionId: basePartition,
    title: "Architecture triage",
    scheduledAt: "2026-07-31T00:00:00.000Z",
    participants: ["planner"],
    provenance: person("planner"),
  });
  const meetingId = meeting.effect?.createdMeetingId || "";
  const firstDecision = store.recordDecision({
    partitionId: basePartition,
    meetingId,
    title: "Choose primary datastore",
    rationale: "Need a stable foundation",
    alternatives: [{ option: "Postgres", rationale: "Familiar operations" }],
    participants: ["planner"],
    evidence: [],
    actions: [
      {
        title: "Write migration plan",
        assigneeId: "planner",
        dueAt: "2026-08-14T00:00:00.000Z",
      },
    ],
    provenance: person("planner"),
  });
  const firstDecisionId = firstDecision.effect?.createdDecisionId || "";
  assert.ok(firstDecisionId);
  assert.strictEqual(store.getDecision(firstDecisionId).status, "adopted");

  const superseding = store.recordDecision({
    partitionId: basePartition,
    meetingId,
    title: "Choose primary datastore (revised)",
    rationale: "Operational evidence changed after review",
    alternatives: [
      { option: "Postgres", rationale: "Retain compatibility" },
      { option: "MySQL", rationale: "Lower infra overhead" },
    ],
    selectedAlternativeIndex: 1,
    participants: ["planner"],
    evidence: ["performance benchmark"],
    supersedesDecisionId: firstDecisionId,
    actions: [
      {
        title: "Update deployment topology",
        assigneeId: "planner",
        dueAt: "2026-08-15T00:00:00.000Z",
      },
    ],
    provenance: person("planner"),
  });
  assert.strictEqual(superseding.effect?.decisionSupersedesDecisionId, firstDecisionId);
  assert.strictEqual(store.getDecision(firstDecisionId).status, "superseded");
  assert.strictEqual(store.getDecision(superseding.effect?.createdDecisionId || "").supersedesDecisionId, firstDecisionId);
  const reverted = store.revertProposal(superseding.proposalId);
  assert.strictEqual(reverted.status, "reverted");
  assert.strictEqual(store.getDecision(firstDecisionId).status, "adopted");
  const restoredCommitments = store.getDecisionActions(firstDecisionId);
  assert.strictEqual(restoredCommitments.length, 1);
});

test("IOTA-03 rejects bad action extraction atomically", () => {
  const store = new IotaDomainStore({ now: fixedNow("2026-08-03T00:00:00.000Z") });
  assert.strictEqual(store.listCommitments(basePartition).length, 0);

  store.proposeMeeting({
    partitionId: basePartition,
    title: "Quarterly check-in",
    scheduledAt: "2026-08-11T00:00:00.000Z",
    participants: ["planner"],
    provenance: person("planner"),
  });

  assert.throws(
    () =>
      store.recordDecision({
        partitionId: basePartition,
        title: "Invalid action due timestamp",
        rationale: "Need cleanup",
        alternatives: [{ option: "Continue", rationale: "No-op" }],
        participants: ["planner"],
        evidence: [],
        actions: [
          {
            title: "Fix broken pipeline",
            assigneeId: "planner",
            dueAt: "not-a-timestamp",
          },
        ],
        provenance: person("planner"),
      }),
    /not a valid timestamp/,
  );
  assert.strictEqual(store.listCommitments(basePartition).length, 0);
});
