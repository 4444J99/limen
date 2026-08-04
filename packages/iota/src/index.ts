import { randomUUID } from "node:crypto";

export const IOTA01_IDENTITY_VERSION = "iota-01-identity-v1";
export const IOTA01_RELATIONSHIP_VERSION = "iota-01-relationship-v1";
export const IOTA01_ENGAGEMENT_VERSION = "iota-01-engagement-v1";
export const IOTA01_TIMELINE_VERSION = "iota-01-timeline-v1";
export const IOTA02_WORK_VERSION = "iota-02-work-v1";
export const IOTA02_MILESTONE_VERSION = "iota-02-milestone-v1";
export const IOTA02_REVIEW_VERSION = "iota-02-review-v1";
export const IOTA02_RISK_VERSION = "iota-02-risk-v1";
export const IOTA03_MEETING_VERSION = "iota-03-meeting-v1";
export const IOTA03_DECISION_VERSION = "iota-03-decision-v1";
export const IOTA03_NOTE_VERSION = "iota-03-note-v1";

export type IotaIdentityKind = "person" | "organization";
export type IotaRelationshipState = "proposed" | "active" | "paused" | "ended";
export type IotaEngagementState = "proposed" | "active" | "complete" | "deferred" | "cancelled";
export type IotaCommitmentState = "open" | "active" | "blocked" | "waiting" | "reopened" | "complete" | "cancelled";
export type IotaMilestoneState = "planned" | "active" | "complete" | "cancelled";
export type IotaReviewQueueState = "open" | "resolved" | "dismissed";
export type IotaRiskLevel = "low" | "medium" | "high";
export type IotaReviewSubject = "commitment" | "milestone" | "risk";
export type IotaMeetingStatus = "planned" | "held" | "cancelled";
export type IotaDecisionState = "proposed" | "adopted" | "superseded" | "closed";
export type ProposalStatus = "open" | "approved" | "rejected" | "reverted";
export type ProposalType =
  | "identity.create"
  | "identity.merge"
  | "relationship.create"
  | "engagement.create"
  | "engagement.state-change"
  | "commitment.create"
  | "commitment.state-change"
  | "milestone.create"
  | "milestone.state-change"
  | "risk.record"
  | "meeting.create"
  | "decision.record";

export interface IotaProvenance {
  actorId: string;
  actorType: string;
  notes?: string;
}

export interface IotaIdentity {
  identityId: string;
  partitionId: string;
  kind: IotaIdentityKind;
  canonicalName: string;
  aliases: readonly string[];
  provenance: IotaProvenance;
  createdAt: string;
  updatedAt: string;
  active: boolean;
  mergedInto?: string;
  replacedBy?: string;
}

export interface IotaRelationship {
  relationshipId: string;
  partitionId: string;
  sourceIdentityId: string;
  targetIdentityId: string;
  relationshipType: string;
  state: IotaRelationshipState;
  provenance: IotaProvenance;
  createdAt: string;
  updatedAt: string;
}

export interface IotaEngagement {
  engagementId: string;
  partitionId: string;
  relationshipId: string;
  title: string;
  state: IotaEngagementState;
  provenance: IotaProvenance;
  createdAt: string;
  updatedAt: string;
}

export interface IotaTimelineEvent {
  eventId: string;
  partitionId: string;
  eventType: string;
  subjectType:
    | "identity"
    | "relationship"
    | "engagement"
    | "commitment"
    | "milestone"
    | "risk"
    | "review"
    | "proposal"
    | "meeting"
    | "decision"
    | "note";
  subjectId: string;
  actorId: string;
  occurredAt: string;
  details: Record<string, unknown>;
  provenance: IotaProvenance;
}

export interface IdentityProposal {
  proposalId: string;
  partitionId: string;
  proposalType: ProposalType;
  status: ProposalStatus;
  input: Record<string, unknown>;
  provenance: IotaProvenance;
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string;
  resolvedBy?: string;
  decisionNotes?: string;
  effect?: IotaProposalEffect;
}

export interface IotaProposalEffect {
  kind: ProposalType;
  createdIdentityId?: string;
  mergedIdentityId?: string;
  keptIdentityId?: string;
  createdRelationshipId?: string;
  createdEngagementId?: string;
  relationshipId?: string;
  createdCommitmentId?: string;
  commitmentId?: string;
  commitmentStateFrom?: IotaCommitmentState;
  commitmentStateTo?: IotaCommitmentState;
  priorEngagementState?: IotaEngagementState;
  createdMilestoneId?: string;
  milestoneId?: string;
  milestoneStateFrom?: IotaMilestoneState;
  milestoneStateTo?: IotaMilestoneState;
  createdRiskId?: string;
  reviewQueueId?: string;
  createdMeetingId?: string;
  createdDecisionId?: string;
  createdNoteId?: string;
  decisionStateFrom?: IotaDecisionState;
  decisionStateTo?: IotaDecisionState;
  decisionSupersedesDecisionId?: string;
  decisionSupersedingDecisionId?: string;
  createdCommitmentIds?: readonly string[];
}

export interface IotaTimelineWindow {
  before?: string;
  after?: string;
  limit?: number;
}

export interface IdentityIdentityInput {
  partitionId: string;
  kind: IotaIdentityKind;
  canonicalName: string;
  aliases?: readonly string[];
  provenance: IotaProvenance;
}

export interface IdentityMergeInput {
  partitionId: string;
  keptIdentityId: string;
  mergedIdentityId: string;
  provenance: IotaProvenance;
}

export interface RelationshipInput {
  partitionId: string;
  sourceIdentityId: string;
  targetIdentityId: string;
  relationshipType: string;
  provenance: IotaProvenance;
}

export interface EngagementInput {
  partitionId: string;
  relationshipId: string;
  title: string;
  provenance: IotaProvenance;
}

export interface TimelineProjection {
  partitionId: string;
  events: IotaTimelineEvent[];
}

export interface IotaMeetingNote {
  noteId: string;
  partitionId: string;
  meetingId: string;
  authorId: string;
  body: string;
  createdAt: string;
}

export interface IotaCommitment {
  commitmentId: string;
  partitionId: string;
  engagementId?: string;
  milestoneId?: string;
  title: string;
  assigneeId: string;
  dueAt: string;
  waitingOn: readonly string[];
  state: IotaCommitmentState;
  provenance: IotaProvenance;
  riskLevel: IotaRiskLevel;
  reopenedCount: number;
  createdAt: string;
  updatedAt: string;
  completedAt?: string;
  cancelledAt?: string;
  sourceDecisionIds: readonly string[];
}

export interface IotaMilestone {
  milestoneId: string;
  partitionId: string;
  title: string;
  dueAt?: string;
  state: IotaMilestoneState;
  commitmentIds: readonly string[];
  provenance: IotaProvenance;
  createdAt: string;
  updatedAt: string;
}

export interface IotaRiskSignal {
  riskId: string;
  partitionId: string;
  subjectType: IotaReviewSubject;
  subjectId: string;
  level: IotaRiskLevel;
  rationale: string;
  observedAt: string;
  resolvedAt?: string;
}

export interface IotaDecisionAlternative {
  option: string;
  rationale: string;
}

export interface IotaMeeting {
  meetingId: string;
  partitionId: string;
  title: string;
  scheduledAt: string;
  status: IotaMeetingStatus;
  participants: readonly string[];
  agenda: readonly string[];
  noteIds: readonly string[];
  decisionIds: readonly string[];
  provenance: IotaProvenance;
  createdAt: string;
  updatedAt: string;
}

export interface IotaDecision {
  decisionId: string;
  partitionId: string;
  meetingId?: string;
  title: string;
  rationale: string;
  alternatives: readonly IotaDecisionAlternative[];
  selectedAlternativeIndex?: number;
  participants: readonly string[];
  evidence: readonly string[];
  status: IotaDecisionState;
  sourceCommitmentIds: readonly string[];
  supersedesDecisionId?: string;
  supersedingDecisionId?: string;
  provenance: IotaProvenance;
  createdAt: string;
  updatedAt: string;
}

export interface IotaMeetingBrief {
  partitionId: string;
  meeting: IotaMeeting;
  notes: IotaMeetingNote[];
  decisions: IotaDecision[];
  actionCommitments: IotaCommitment[];
  openActionCommitments: IotaCommitment[];
  timeline: IotaTimelineEvent[];
}

export interface IotaReviewQueueItem {
  reviewId: string;
  partitionId: string;
  subjectType: IotaReviewSubject;
  subjectId: string;
  reason: string;
  status: IotaReviewQueueState;
  requestedBy: string;
  requestedAt: string;
  resolvedBy?: string;
  resolvedAt?: string;
  resolution?: string;
}

export interface IotaTaskInput {
  partitionId: string;
  title: string;
  assigneeId: string;
  dueAt: string;
  waitingOn?: readonly string[];
  riskLevel?: IotaRiskLevel;
  engagementId?: string;
  milestoneId?: string;
  provenance: IotaProvenance;
}

export interface IotaTaskTransitionInput {
  commitmentId: string;
  nextState: IotaCommitmentState;
  rationale?: string;
  assigneeId?: string;
  dueAt?: string;
  waitingOn?: readonly string[];
  provenance: IotaProvenance;
}

export interface IotaMilestoneInput {
  partitionId: string;
  title: string;
  dueAt?: string;
  provenance: IotaProvenance;
}

export interface IotaMilestoneTransitionInput {
  milestoneId: string;
  nextState: IotaMilestoneState;
  rationale?: string;
  provenance: IotaProvenance;
}

export interface IotaRiskInput {
  partitionId: string;
  subjectType: IotaReviewSubject;
  subjectId: string;
  level: IotaRiskLevel;
  rationale: string;
  provenance: IotaProvenance;
}

export interface IotaMeetingInput {
  partitionId: string;
  title: string;
  scheduledAt: string;
  participants: readonly string[];
  agenda?: readonly string[];
  provenance: IotaProvenance;
}

export interface IotaDecisionActionInput {
  title: string;
  assigneeId: string;
  dueAt: string;
  waitingOn?: readonly string[];
  riskLevel?: IotaRiskLevel;
  engagementId?: string;
  milestoneId?: string;
}

export interface IotaDecisionInput {
  partitionId: string;
  meetingId?: string;
  title: string;
  rationale: string;
  alternatives: readonly IotaDecisionAlternative[];
  selectedAlternativeIndex?: number;
  participants: readonly string[];
  evidence: readonly string[];
  supersedesDecisionId?: string;
  actions?: readonly IotaDecisionActionInput[];
  provenance: IotaProvenance;
}

export interface IotaMeetingNoteInput {
  partitionId: string;
  meetingId: string;
  authorId: string;
  body: string;
  provenance: IotaProvenance;
}

export interface IotaReviewInput {
  partitionId: string;
  subjectType: IotaReviewSubject;
  subjectId: string;
  reason: string;
  provenance: IotaProvenance;
}

interface IotaStoreState {
  identities: Map<string, IotaIdentity>;
  relationships: Map<string, IotaRelationship>;
  engagements: Map<string, IotaEngagement>;
  proposals: Map<string, IdentityProposal>;
  timeline: Map<string, IotaTimelineEvent[]>;
  commitments: Map<string, IotaCommitment>;
  milestones: Map<string, IotaMilestone>;
  riskSignals: Map<string, IotaRiskSignal>;
  reviewQueue: Map<string, IotaReviewQueueItem>;
  meetings: Map<string, IotaMeeting>;
  decisions: Map<string, IotaDecision>;
  meetingNotes: Map<string, IotaMeetingNote>;
}

interface ClockOptions {
  now?: () => string;
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right));
  return `{${entries.map(([key, nested]) => `${JSON.stringify(key)}:${stableStringify(nested)}`).join(",")}}`;
}

function toIdentitySnapshot(value: IotaIdentity): IotaIdentity {
  return { ...value, aliases: [...value.aliases] };
}

function toRelationshipSnapshot(value: IotaRelationship): IotaRelationship {
  return { ...value };
}

function toEngagementSnapshot(value: IotaEngagement): IotaEngagement {
  return { ...value };
}

function deepCopy<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function sortByOccurredAt(a: IotaTimelineEvent, b: IotaTimelineEvent): number {
  const at = Date.parse(a.occurredAt) - Date.parse(b.occurredAt);
  if (at !== 0) {
    return at;
  }
  return a.eventId.localeCompare(b.eventId);
}

export class IotaDomainStore {
  private state: IotaStoreState;
  private now: () => string;

  public constructor(options?: ClockOptions) {
    this.state = {
      identities: new Map(),
      relationships: new Map(),
      engagements: new Map(),
      proposals: new Map(),
      timeline: new Map(),
      commitments: new Map(),
      milestones: new Map(),
      riskSignals: new Map(),
      reviewQueue: new Map(),
      meetings: new Map(),
      decisions: new Map(),
      meetingNotes: new Map(),
    };
    this.now = options?.now || (() => new Date().toISOString());
  }

  public proposeIdentity(input: IdentityIdentityInput): IdentityProposal {
    this.validateNonEmpty(input.partitionId, "partitionId");
    this.validateNonEmpty(input.kind, "kind");
    const proposal = this.newProposal("identity.create", input.partitionId, {
      kind: input.kind,
      canonicalName: input.canonicalName,
      aliases: [...(input.aliases || [])],
      provenance: input.provenance,
    });
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(input.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      details: {
        proposalType: proposal.proposalType,
        identityKind: input.kind,
        canonicalName: input.canonicalName,
      },
      provenance: input.provenance,
    });
    return deepCopy(proposal);
  }

  public proposeIdentityMerge(input: IdentityMergeInput): IdentityProposal {
    this.assertSamePartition(input.partitionId, input.keptIdentityId, input.mergedIdentityId);

    const proposal = this.newProposal("identity.merge", input.partitionId, {
      keptIdentityId: input.keptIdentityId,
      mergedIdentityId: input.mergedIdentityId,
      provenance: input.provenance,
    });
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(input.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      details: {
        proposalType: proposal.proposalType,
        keptIdentityId: input.keptIdentityId,
        mergedIdentityId: input.mergedIdentityId,
      },
      provenance: input.provenance,
    });
    return deepCopy(proposal);
  }

  public proposeRelationship(input: RelationshipInput): IdentityProposal {
    this.assertDifferentIdentityRefs(input.sourceIdentityId, input.targetIdentityId);
    this.assertSamePartition(input.partitionId, input.sourceIdentityId, input.targetIdentityId);

    const proposal = this.newProposal("relationship.create", input.partitionId, {
      sourceIdentityId: input.sourceIdentityId,
      targetIdentityId: input.targetIdentityId,
      relationshipType: input.relationshipType,
      provenance: input.provenance,
    });
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(input.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      details: {
        proposalType: proposal.proposalType,
        relationshipType: input.relationshipType,
      },
      provenance: input.provenance,
    });
    return deepCopy(proposal);
  }

  public proposeEngagement(input: EngagementInput): IdentityProposal {
    const relationship = this.getRelationship(input.relationshipId);
    if (relationship.partitionId !== input.partitionId) {
      throw new Error("proposal partition mismatch");
    }

    const proposal = this.newProposal("engagement.create", input.partitionId, {
      relationshipId: input.relationshipId,
      title: input.title,
      provenance: input.provenance,
    });
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(input.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      details: {
        proposalType: proposal.proposalType,
        relationshipId: input.relationshipId,
      },
      provenance: input.provenance,
    });
    return deepCopy(proposal);
  }

  public proposeCommitment(input: IotaTaskInput): IdentityProposal {
    const assignment = input.assigneeId;
    this.validateNonEmpty(input.title, "title");
    this.validateNonEmpty(assignment, "assigneeId");
    this.validateTimestamp(input.dueAt, "dueAt");

    const proposal = this.newProposal("commitment.create", input.partitionId, {
      title: input.title,
      assigneeId: input.assigneeId,
      dueAt: input.dueAt,
      waitingOn: [...(input.waitingOn || [])],
      engagementId: input.engagementId,
      milestoneId: input.milestoneId,
      riskLevel: input.riskLevel || "low",
      provenance: input.provenance,
    });
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(input.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      actorId: input.provenance.actorId,
      details: {
        proposalType: proposal.proposalType,
        title: input.title,
      },
      provenance: input.provenance,
    });
    return deepCopy(proposal);
  }

  public proposeMilestone(input: IotaMilestoneInput): IdentityProposal {
    this.validateNonEmpty(input.title, "title");
    if (input.dueAt) {
      this.validateTimestamp(input.dueAt, "dueAt");
    }

    const proposal = this.newProposal("milestone.create", input.partitionId, {
      title: input.title,
      dueAt: input.dueAt,
      provenance: input.provenance,
    });
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(input.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      actorId: input.provenance.actorId,
      details: {
        proposalType: proposal.proposalType,
        title: input.title,
      },
      provenance: input.provenance,
    });
    return deepCopy(proposal);
  }

  public proposeMilestoneTransition(input: IotaMilestoneTransitionInput): IdentityProposal {
    const milestone = this.getMilestone(input.milestoneId);
    this.validateMilestoneTransition(milestone.state, input.nextState);
    const proposal = this.newProposal("milestone.state-change", milestone.partitionId, {
      milestoneId: input.milestoneId,
      nextState: input.nextState,
      rationale: input.rationale,
      provenance: input.provenance,
    });
    proposal.status = "open";
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(milestone.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      actorId: input.provenance.actorId,
      details: {
        proposalType: proposal.proposalType,
        milestoneId: input.milestoneId,
        nextState: input.nextState,
      },
      provenance: input.provenance,
    });
    return this.approveProposal(proposal.proposalId);
  }

  public proposeCommitmentTransition(input: IotaTaskTransitionInput): IdentityProposal {
    const commitment = this.getCommitment(input.commitmentId);
    this.validateCommitmentTransition(commitment.state, input.nextState);
    if (input.assigneeId) {
      this.validateNonEmpty(input.assigneeId, "assigneeId");
    }
    if (input.dueAt) {
      this.validateTimestamp(input.dueAt, "dueAt");
    }

    const proposal = this.newProposal("commitment.state-change", commitment.partitionId, {
      commitmentId: input.commitmentId,
      fromState: commitment.state,
      nextState: input.nextState,
      rationale: input.rationale,
      assigneeId: input.assigneeId,
      dueAt: input.dueAt,
      waitingOn: [...(input.waitingOn || [])],
      provenance: input.provenance,
    });
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(commitment.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      actorId: input.provenance.actorId,
      details: {
        proposalType: proposal.proposalType,
        commitmentId: input.commitmentId,
        nextState: input.nextState,
      },
      provenance: input.provenance,
    });
    return this.approveProposal(proposal.proposalId);
  }

  public proposeMeeting(input: IotaMeetingInput): IdentityProposal {
    this.validateNonEmpty(input.partitionId, "partitionId");
    this.validateNonEmpty(input.title, "title");
    this.validateTimestamp(input.scheduledAt, "scheduledAt");
    if (!Array.isArray(input.participants) || input.participants.length === 0) {
      throw new Error("meeting participants are required");
    }
    for (const participantId of input.participants) {
      this.validateNonEmpty(participantId, "participantId");
    }

    const proposal = this.newProposal("meeting.create", input.partitionId, {
      title: input.title,
      scheduledAt: input.scheduledAt,
      participants: [...input.participants],
      agenda: [...(input.agenda || [])],
      provenance: input.provenance,
    });
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(input.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      actorId: input.provenance.actorId,
      details: {
        proposalType: proposal.proposalType,
        title: input.title,
        participants: input.participants,
      },
      provenance: input.provenance,
    });
    return this.approveProposal(proposal.proposalId);
  }

  public recordDecision(input: IotaDecisionInput): IdentityProposal {
    this.validateNonEmpty(input.title, "title");
    this.validateNonEmpty(input.rationale, "rationale");
    if (!Array.isArray(input.alternatives) || input.alternatives.length === 0) {
      throw new Error("decision alternatives are required");
    }
    if (!Array.isArray(input.participants) || input.participants.length === 0) {
      throw new Error("decision participants are required");
    }
    const evidence = Array.isArray(input.evidence) ? [...input.evidence] : [];
    if (evidence.length > 0) {
      for (const item of evidence) {
        this.validateNonEmpty(item, "evidence");
      }
    }

    for (const participantId of input.participants) {
      this.validateNonEmpty(participantId, "participantId");
    }
    if (typeof input.selectedAlternativeIndex !== "undefined") {
      if (
        !Number.isInteger(input.selectedAlternativeIndex)
        || input.selectedAlternativeIndex < 0
        || input.selectedAlternativeIndex >= input.alternatives.length
      ) {
        throw new Error("selectedAlternativeIndex is out of range");
      }
    }
    for (const alternative of input.alternatives) {
      this.validateNonEmpty(alternative.option, "alternative.option");
      this.validateNonEmpty(alternative.rationale, "alternative.rationale");
    }

    const proposal = this.newProposal("decision.record", input.partitionId, {
      meetingId: input.meetingId,
      title: input.title,
      rationale: input.rationale,
      alternatives: [...input.alternatives],
      selectedAlternativeIndex: input.selectedAlternativeIndex,
      participants: [...input.participants],
      evidence: [...evidence],
      supersedesDecisionId: input.supersedesDecisionId,
      actions: [...(input.actions || [])],
      provenance: input.provenance,
    });
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(input.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      actorId: input.provenance.actorId,
      details: {
        proposalType: proposal.proposalType,
        title: input.title,
        meetingId: input.meetingId,
      },
      provenance: input.provenance,
    });
    return this.approveProposal(proposal.proposalId);
  }

  public addMeetingNote(input: IotaMeetingNoteInput): IotaMeetingNote {
    this.validateNonEmpty(input.partitionId, "partitionId");
    this.validateNonEmpty(input.meetingId, "meetingId");
    this.validateNonEmpty(input.authorId, "authorId");
    this.validateNonEmpty(input.body, "body");

    const meeting = this.getMeeting(input.meetingId);
    if (meeting.partitionId !== input.partitionId) {
      throw new Error("partition leak: meeting partition mismatch");
    }

    const note: IotaMeetingNote = {
      noteId: randomUUID(),
      partitionId: input.partitionId,
      meetingId: input.meetingId,
      authorId: input.authorId,
      body: input.body,
      createdAt: this.now(),
    };
    this.state.meetingNotes.set(note.noteId, note);

    const updatedMeeting = {
      ...meeting,
      noteIds: [...meeting.noteIds, note.noteId],
      updatedAt: this.now(),
    };
    this.state.meetings.set(input.meetingId, updatedMeeting);

    this.appendTimelineEvent(input.partitionId, {
      eventType: "meeting.note.added",
      subjectType: "note",
      subjectId: note.noteId,
      actorId: input.authorId,
      details: {
        meetingId: input.meetingId,
        body: input.body,
      },
      provenance: input.provenance,
    });

    return deepCopy(note);
  }

  public requestReview(input: IotaReviewInput): IotaReviewQueueItem {
    this.validateNonEmpty(input.partitionId, "partitionId");
    this.validateNonEmpty(input.reason, "reason");
    this.validateNonEmpty(input.subjectType, "subjectType");
    this.validateNonEmpty(input.subjectId, "subjectId");
    const review: IotaReviewQueueItem = {
      reviewId: randomUUID(),
      partitionId: input.partitionId,
      subjectType: input.subjectType,
      subjectId: input.subjectId,
      reason: input.reason,
      status: "open",
      requestedBy: input.provenance.actorId,
      requestedAt: this.now(),
    };
    this.state.reviewQueue.set(review.reviewId, review);
    this.appendTimelineEvent(input.partitionId, {
      eventType: "review.requested",
      subjectType: "review",
      subjectId: review.reviewId,
      actorId: input.provenance.actorId,
      details: {
        reason: input.reason,
        subjectType: input.subjectType,
        subjectId: input.subjectId,
      },
      provenance: input.provenance,
    });
    return deepCopy(review);
  }

  public resolveReview(reviewId: string, status: "resolved" | "dismissed", notes: string, actor: IotaProvenance): IotaReviewQueueItem {
    const review = this.state.reviewQueue.get(reviewId);
    if (!review) {
      throw new Error(`missing review item: ${reviewId}`);
    }
    if (review.status !== "open") {
      throw new Error(`review item already ${review.status}`);
    }

    review.status = status;
    review.resolvedBy = actor.actorId;
    review.resolvedAt = this.now();
    review.resolution = notes;
    this.state.reviewQueue.set(reviewId, review);
    this.appendTimelineEvent(review.partitionId, {
      eventType: `review.${status}`,
      subjectType: "review",
      subjectId: reviewId,
      actorId: actor.actorId,
      details: {
        subjectType: review.subjectType,
        subjectId: review.subjectId,
        notes,
      },
      provenance: actor,
    });
    return deepCopy(review);
  }

  public recordRisk(input: IotaRiskInput): IdentityProposal {
    this.validateNonEmpty(input.rationale, "rationale");
    const proposal = this.newProposal("risk.record", input.partitionId, {
      subjectType: input.subjectType,
      subjectId: input.subjectId,
      level: input.level,
      rationale: input.rationale,
      provenance: input.provenance,
    });
    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(input.partitionId, {
      eventType: "proposal.created",
      subjectType: "proposal",
      subjectId: proposal.proposalId,
      actorId: input.provenance.actorId,
      details: {
        proposalType: proposal.proposalType,
        subjectType: input.subjectType,
        subjectId: input.subjectId,
      },
      provenance: input.provenance,
    });
    return this.approveProposal(proposal.proposalId);
  }

  public listCommitments(partitionId: string): IotaCommitment[] {
    return Array.from(this.state.commitments.values())
      .filter((commitment) => commitment.partitionId === partitionId)
      .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))
      .map((commitment) => deepCopy(commitment));
  }

  public listMilestones(partitionId: string): IotaMilestone[] {
    return Array.from(this.state.milestones.values())
      .filter((milestone) => milestone.partitionId === partitionId)
      .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))
      .map((milestone) => deepCopy(milestone));
  }

  public getCommitment(commitmentId: string): IotaCommitment {
    const commitment = this.state.commitments.get(commitmentId);
    if (!commitment) {
      throw new Error(`missing commitment: ${commitmentId}`);
    }
    return deepCopy(commitment);
  }

  public getMilestone(milestoneId: string): IotaMilestone {
    const milestone = this.state.milestones.get(milestoneId);
    if (!milestone) {
      throw new Error(`missing milestone: ${milestoneId}`);
    }
    return deepCopy(milestone);
  }

  public listOverdueCommitments(partitionId: string, asOf = this.now()): IotaCommitment[] {
    const horizon = Date.parse(asOf);
    return this.listCommitments(partitionId)
      .filter((item) => this.isActiveTask(item.state))
      .filter((item) => Date.parse(item.dueAt) <= horizon)
      .map((item) => deepCopy(item));
  }

  public listWaitingCommitments(partitionId: string): IotaCommitment[] {
    return this.listCommitments(partitionId)
      .filter((item) => item.state === "waiting" || item.waitingOn.length > 0)
      .map((item) => deepCopy(item));
  }

  public listAtRiskCommitments(partitionId: string, asOf = this.now()): IotaCommitment[] {
    const horizon = Date.parse(asOf);
    return this.listCommitments(partitionId)
      .filter((item) => this.isActiveTask(item.state))
      .filter((item) => item.riskLevel === "high" || Date.parse(item.dueAt) <= horizon + 48 * 60 * 60 * 1000)
      .map((item) => deepCopy(item));
  }

  public listStaleCommitments(partitionId: string, asOf = this.now(), maxStaleMs = 14 * 24 * 60 * 60 * 1000): IotaCommitment[] {
    const asOfMillis = Date.parse(asOf);
    return this.listCommitments(partitionId)
      .filter((item) => this.isActiveTask(item.state))
      .filter((item) => asOfMillis - Date.parse(item.updatedAt) > maxStaleMs)
      .map((item) => deepCopy(item));
  }

  public listNextActions(partitionId: string, asOf = this.now(), limit = 25): IotaCommitment[] {
    return this.listCommitments(partitionId)
      .filter((item) => this.isActiveTask(item.state))
      .sort((left, right) => {
        const byState = this.commitmentPriorityState(right.state) - this.commitmentPriorityState(left.state);
        if (byState !== 0) {
          return byState;
        }
        const due = Date.parse(left.dueAt) - Date.parse(right.dueAt);
        if (due !== 0) {
          return due;
        }
        return Date.parse(left.updatedAt) - Date.parse(right.updatedAt);
      })
      .slice(0, limit)
      .map((item) => deepCopy(item));
  }

  public listReviewQueue(partitionId: string, includeResolved = false): IotaReviewQueueItem[] {
    return Array.from(this.state.reviewQueue.values())
      .filter((entry) => entry.partitionId === partitionId)
      .filter((entry) => includeResolved || entry.status === "open")
      .sort((left, right) => Date.parse(right.requestedAt) - Date.parse(left.requestedAt))
      .map((entry) => deepCopy(entry));
  }

  public listMeetings(partitionId: string): IotaMeeting[] {
    return Array.from(this.state.meetings.values())
      .filter((meeting) => meeting.partitionId === partitionId)
      .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))
      .map((meeting) => deepCopy(meeting));
  }

  public listDecisions(partitionId: string, includeSuperseded = false): IotaDecision[] {
    return Array.from(this.state.decisions.values())
      .filter((decision) => decision.partitionId === partitionId)
      .filter((decision) => includeSuperseded || decision.status !== "superseded")
      .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))
      .map((decision) => deepCopy(decision));
  }

  public getMeeting(meetingId: string): IotaMeeting {
    const meeting = this.state.meetings.get(meetingId);
    if (!meeting) {
      throw new Error(`missing meeting: ${meetingId}`);
    }
    return deepCopy(meeting);
  }

  public getDecision(decisionId: string): IotaDecision {
    const decision = this.state.decisions.get(decisionId);
    if (!decision) {
      throw new Error(`missing decision: ${decisionId}`);
    }
    return deepCopy(decision);
  }

  public getMeetingNotes(meetingId: string): IotaMeetingNote[] {
    const meeting = this.getMeeting(meetingId);
    return Array.from(this.state.meetingNotes.values())
      .filter((note) => note.meetingId === meetingId && note.partitionId === meeting.partitionId)
      .sort((left, right) => Date.parse(left.createdAt) - Date.parse(right.createdAt))
      .map((note) => deepCopy(note));
  }

  public getDecisionActions(decisionId: string): IotaCommitment[] {
    const decision = this.getDecision(decisionId);
    return decision.sourceCommitmentIds
      .map((commitmentId) => this.getCommitment(commitmentId))
      .filter((commitment) => commitment.partitionId === decision.partitionId)
      .map((commitment) => deepCopy(commitment));
  }

  public buildMeetingBrief(meetingId: string): IotaMeetingBrief {
    const meeting = this.getMeeting(meetingId);
    const decisions = this.listDecisions(meeting.partitionId)
      .filter((decision) => decision.meetingId === meetingId)
      .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt));
    const actionCommitmentIds = decisions.flatMap((decision) => [...decision.sourceCommitmentIds]);
    const actionCommitments = Array.from(new Set(actionCommitmentIds)).map((commitmentId) => this.getCommitment(commitmentId));
    const openActionCommitments = actionCommitments
      .filter((commitment) => this.isActiveTask(commitment.state))
      .sort((left, right) => Date.parse(left.dueAt) - Date.parse(right.dueAt));
    const notes = this.getMeetingNotes(meetingId);
    const timeline = this.getTimeline(meeting.partitionId, {
      after: meeting.scheduledAt,
      limit: 25,
    }).events;
    return {
      partitionId: meeting.partitionId,
      meeting,
      notes,
      decisions,
      actionCommitments: actionCommitments.map((commitment) => deepCopy(commitment)),
      openActionCommitments: openActionCommitments.map((commitment) => deepCopy(commitment)),
      timeline: timeline.map((event) => deepCopy(event)),
    };
  }

  public getRisksForCommitment(commitmentId: string): IotaRiskSignal[] {
    return Array.from(this.state.riskSignals.values())
      .filter((risk) => risk.subjectType === "commitment" && risk.subjectId === commitmentId && !risk.resolvedAt)
      .map((risk) => deepCopy(risk));
  }

  public approveProposal(proposalId: string): IdentityProposal {
    const proposal = this.requireProposal(proposalId);
    if (proposal.status !== "open") {
      throw new Error(`proposal status ${proposal.status} is not open`);
    }

    const now = this.now();
    proposal.status = "approved";
    proposal.updatedAt = now;
    proposal.resolvedAt = now;
    proposal.resolvedBy = proposal.provenance.actorId;

    if (proposal.proposalType === "identity.create") {
      const input = proposal.input as {
        kind: IotaIdentityKind;
        canonicalName: string;
        aliases: string[];
      };
      const identity = this.createIdentity(partitionFromInput(proposal), input.kind, input.canonicalName, input.aliases, proposal.provenance);
      proposal.effect = { kind: "identity.create", createdIdentityId: identity.identityId };
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "identity.created",
        subjectType: "identity",
        subjectId: identity.identityId,
        details: {
          kind: identity.kind,
          canonicalName: identity.canonicalName,
        },
        provenance: proposal.provenance,
      });
    } else if (proposal.proposalType === "identity.merge") {
      const input = proposal.input as {
        keptIdentityId: string;
        mergedIdentityId: string;
      };
      const merged = this.applyIdentityMerge(input.keptIdentityId, input.mergedIdentityId, proposal.provenance);
      proposal.effect = {
        kind: "identity.merge",
        keptIdentityId: input.keptIdentityId,
        mergedIdentityId: input.mergedIdentityId,
      };
      this.appendTimelineEvent(merged.partitionId, {
        eventType: "identity.merged",
        subjectType: "identity",
        subjectId: input.keptIdentityId,
        details: {
          mergedIdentityId: input.mergedIdentityId,
        },
        provenance: proposal.provenance,
      });
    } else if (proposal.proposalType === "relationship.create") {
      const input = proposal.input as {
        sourceIdentityId: string;
        targetIdentityId: string;
        relationshipType: string;
      };
      const relationship = this.createRelationship(
        partitionFromInput(proposal),
        input.sourceIdentityId,
        input.targetIdentityId,
        input.relationshipType,
        proposal.provenance,
      );
      proposal.effect = {
        kind: "relationship.create",
        createdRelationshipId: relationship.relationshipId,
      };
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "relationship.created",
        subjectType: "relationship",
        subjectId: relationship.relationshipId,
        details: {
          sourceIdentityId: relationship.sourceIdentityId,
          targetIdentityId: relationship.targetIdentityId,
          relationshipType: relationship.relationshipType,
        },
        provenance: proposal.provenance,
      });
    } else if (proposal.proposalType === "engagement.create") {
      const input = proposal.input as {
        relationshipId: string;
        title: string;
      };
      const relation = this.getRelationship(input.relationshipId);
      const engagement = this.createEngagement(relation.partitionId, input.relationshipId, input.title, proposal.provenance);
      proposal.effect = {
        kind: "engagement.create",
        createdEngagementId: engagement.engagementId,
        relationshipId: engagement.relationshipId,
      };
      this.appendTimelineEvent(relation.partitionId, {
        eventType: "engagement.created",
        subjectType: "engagement",
        subjectId: engagement.engagementId,
        details: {
          title: engagement.title,
          relationshipId: engagement.relationshipId,
        },
        provenance: proposal.provenance,
      });
    } else if (proposal.proposalType === "commitment.create") {
      const input = proposal.input as {
        title: string;
        assigneeId: string;
        dueAt: string;
        waitingOn: string[];
        engagementId?: string;
        milestoneId?: string;
        riskLevel?: IotaRiskLevel;
      };
      const commitment = this.createCommitment(
        partitionFromInput(proposal),
        input.title,
        input.assigneeId,
        input.dueAt,
        input.waitingOn,
        input.engagementId,
        input.milestoneId,
        input.riskLevel || "low",
        proposal.provenance,
      );
      proposal.effect = {
        kind: "commitment.create",
        createdCommitmentId: commitment.commitmentId,
      };
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "commitment.created",
        subjectType: "commitment",
        subjectId: commitment.commitmentId,
        actorId: proposal.provenance.actorId,
        details: {
          title: commitment.title,
          assigneeId: commitment.assigneeId,
          dueAt: commitment.dueAt,
          riskLevel: commitment.riskLevel,
        },
        provenance: proposal.provenance,
      });
      if (commitment.milestoneId) {
        this.linkCommitmentToMilestone(commitment.commitmentId, commitment.milestoneId);
      }
    } else if (proposal.proposalType === "commitment.state-change") {
      const input = proposal.input as {
        commitmentId: string;
        nextState: IotaCommitmentState;
        rationale?: string;
        assigneeId?: string;
        dueAt?: string;
        waitingOn: string[];
      };
      const commitment = this.getCommitment(input.commitmentId);
      const fromState = commitment.state;
      this.applyCommitmentTransition(
        commitment,
        input.nextState,
        proposal.provenance,
        input.rationale,
        input.assigneeId,
        input.dueAt,
        input.waitingOn,
      );
      proposal.effect = {
        kind: "commitment.state-change",
        commitmentId: input.commitmentId,
        commitmentStateFrom: fromState,
        commitmentStateTo: input.nextState,
      };
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "commitment.state.changed",
        subjectType: "commitment",
        subjectId: input.commitmentId,
        actorId: proposal.provenance.actorId,
        details: {
          state: input.nextState,
          rationale: input.rationale,
          assigneeId: input.assigneeId,
          dueAt: input.dueAt,
          waitingOn: input.waitingOn,
        },
        provenance: proposal.provenance,
      });
      if (input.nextState === "blocked" || input.nextState === "cancelled") {
        const queueId = this.createReviewRequestFromProposal(
          commitment.partitionId,
          {
            reviewSubjectType: "commitment",
            reviewSubjectId: input.commitmentId,
            reason: `commitment entered ${input.nextState}`,
          },
          proposal.provenance,
        );
        proposal.effect.reviewQueueId = queueId;
      }
    } else if (proposal.proposalType === "milestone.create") {
      const input = proposal.input as {
        title: string;
        dueAt?: string;
      };
      const milestone = this.createMilestone(partitionFromInput(proposal), input.title, input.dueAt, proposal.provenance);
      proposal.effect = {
        kind: "milestone.create",
        createdMilestoneId: milestone.milestoneId,
      };
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "milestone.created",
        subjectType: "milestone",
        subjectId: milestone.milestoneId,
        actorId: proposal.provenance.actorId,
        details: {
          title: milestone.title,
          dueAt: milestone.dueAt,
        },
        provenance: proposal.provenance,
      });
    } else if (proposal.proposalType === "milestone.state-change") {
      const input = proposal.input as {
        milestoneId: string;
        nextState: IotaMilestoneState;
        rationale?: string;
      };
      const milestone = this.getMilestone(input.milestoneId);
      this.applyMilestoneTransition(milestone, input.nextState);
      proposal.effect = {
        kind: "milestone.state-change",
        milestoneId: input.milestoneId,
        milestoneStateFrom: milestone.state,
        milestoneStateTo: input.nextState,
      };
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "milestone.state.changed",
        subjectType: "milestone",
        subjectId: input.milestoneId,
        actorId: proposal.provenance.actorId,
        details: {
          nextState: input.nextState,
          rationale: input.rationale,
        },
        provenance: proposal.provenance,
      });
    } else if (proposal.proposalType === "risk.record") {
      const input = proposal.input as {
        subjectType: IotaReviewSubject;
        subjectId: string;
        level: IotaRiskLevel;
        rationale: string;
      };
      const risk = this.createRiskSignal(
        partitionFromInput(proposal),
        input.subjectType,
        input.subjectId,
        input.level,
        input.rationale,
        proposal.provenance,
      );
      proposal.effect = {
        kind: "risk.record",
        createdRiskId: risk.riskId,
      };
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "risk.recorded",
        subjectType: input.subjectType === "commitment" ? "commitment" : input.subjectType === "milestone" ? "milestone" : "risk",
        subjectId: input.subjectId,
        actorId: proposal.provenance.actorId,
        details: {
          subjectType: input.subjectType,
          level: input.level,
          rationale: input.rationale,
          riskId: risk.riskId,
        },
        provenance: proposal.provenance,
      });
      if (input.level === "high") {
        const queueId = this.createReviewRequestFromProposal(
          partitionFromInput(proposal),
          {
            reviewSubjectType: "risk",
            reviewSubjectId: risk.riskId,
            reason: "high severity risk recorded",
          },
          proposal.provenance,
        );
        proposal.effect.reviewQueueId = queueId;
      }
    } else if (proposal.proposalType === "meeting.create") {
      const input = proposal.input as {
        title: string;
        scheduledAt: string;
        participants: readonly string[];
        agenda: readonly string[];
      };
      const meeting = this.createMeeting(
        partitionFromInput(proposal),
        input.title,
        input.scheduledAt,
        [...input.participants],
        [...input.agenda],
        proposal.provenance,
      );
      proposal.effect = {
        kind: "meeting.create",
        createdMeetingId: meeting.meetingId,
      };
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "meeting.created",
        subjectType: "meeting",
        subjectId: meeting.meetingId,
        actorId: proposal.provenance.actorId,
        details: {
          title: meeting.title,
          scheduledAt: meeting.scheduledAt,
        },
        provenance: proposal.provenance,
      });
    } else if (proposal.proposalType === "decision.record") {
      const input = proposal.input as {
        meetingId?: string;
        title: string;
        rationale: string;
        alternatives: readonly IotaDecisionAlternative[];
        selectedAlternativeIndex?: number;
        participants: readonly string[];
        evidence: readonly string[];
        supersedesDecisionId?: string;
        actions: readonly IotaDecisionActionInput[];
      };
      const result = this.createDecisionAndTasks(
        partitionFromInput(proposal),
        proposal.provenance,
        {
          meetingId: input.meetingId,
          title: input.title,
          rationale: input.rationale,
          alternatives: [...input.alternatives],
          selectedAlternativeIndex: input.selectedAlternativeIndex,
          participants: [...input.participants],
          evidence: [...input.evidence],
          supersedesDecisionId: input.supersedesDecisionId,
          actions: [...(input.actions || [])],
        },
      );
      proposal.effect = {
        kind: "decision.record",
        createdDecisionId: result.decision.decisionId,
        createdCommitmentIds: [...result.commitmentIds],
        decisionStateTo: result.decision.status,
        decisionStateFrom: result.supersededDecisionPreviousState,
        decisionSupersedesDecisionId: result.supersededDecision ? result.supersededDecision.decisionId : undefined,
      };

      if (result.supersededDecision) {
        proposal.effect.decisionSupersedingDecisionId = result.decision.decisionId;
      }

      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "decision.recorded",
        subjectType: "decision",
        subjectId: result.decision.decisionId,
        actorId: proposal.provenance.actorId,
        details: {
          title: result.decision.title,
          meetingId: result.decision.meetingId,
          alternatives: result.decision.alternatives,
          actions: result.commitmentIds,
          supersedesDecisionId: result.supersededDecision?.decisionId,
        },
        provenance: proposal.provenance,
      });
      if (result.supersededDecision) {
        this.appendTimelineEvent(partitionFromInput(proposal), {
          eventType: "decision.superseded",
          subjectType: "decision",
          subjectId: result.supersededDecision.decisionId,
          actorId: proposal.provenance.actorId,
          details: {
            supersedingDecisionId: result.decision.decisionId,
          },
          provenance: proposal.provenance,
        });
      }
    }

    this.state.proposals.set(proposalId, proposal);
    return deepCopy(proposal);
  }

  public rejectProposal(proposalId: string, decisionNotes?: string): IdentityProposal {
    const proposal = this.requireProposal(proposalId);
    if (proposal.status !== "open") {
      throw new Error(`proposal status ${proposal.status} is not open`);
    }

    const now = this.now();
    proposal.status = "rejected";
    proposal.updatedAt = now;
    proposal.resolvedAt = now;
    proposal.resolvedBy = proposal.provenance.actorId;
    proposal.decisionNotes = decisionNotes;

    this.state.proposals.set(proposalId, proposal);
    this.appendTimelineEvent(partitionFromInput(proposal), {
      eventType: "proposal.rejected",
      subjectType: "proposal",
      subjectId: proposalId,
      details: {
        proposalType: proposal.proposalType,
        decisionNotes,
      },
      provenance: proposal.provenance,
    });

    return deepCopy(proposal);
  }

  public revertProposal(proposalId: string): IdentityProposal {
    const proposal = this.requireProposal(proposalId);
    if (proposal.status !== "approved") {
      throw new Error(`proposal status ${proposal.status} cannot be reverted`);
    }

    const now = this.now();

    const effect = proposal.effect;
    if (!effect) {
      throw new Error("proposal has no effect to revert");
    }

    if (effect.kind === "identity.create" && effect.createdIdentityId) {
      this.state.identities.delete(effect.createdIdentityId);
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "identity.created.reverted",
        subjectType: "proposal",
        subjectId: proposalId,
        details: { createdIdentityId: effect.createdIdentityId },
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "identity.merge" && effect.keptIdentityId && effect.mergedIdentityId) {
      const merged = this.state.identities.get(effect.mergedIdentityId);
      if (!merged) {
        throw new Error("merged identity missing during revert");
      }
      const reverted = {
        ...merged,
        active: true,
        mergedInto: undefined,
        replacedBy: undefined,
      };
      this.state.identities.set(reverted.identityId, reverted);
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "identity.merge.reverted",
        subjectType: "identity",
        subjectId: effect.keptIdentityId,
        details: { mergedIdentityId: effect.mergedIdentityId },
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "relationship.create" && effect.createdRelationshipId) {
      const relationship = this.state.relationships.get(effect.createdRelationshipId);
      if (!relationship) {
        throw new Error("relationship missing during revert");
      }
      this.state.relationships.delete(effect.createdRelationshipId);
      this.appendTimelineEvent(relationship.partitionId, {
        eventType: "relationship.created.reverted",
        subjectType: "relationship",
        subjectId: relationship.relationshipId,
        details: {},
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "engagement.create" && effect.createdEngagementId) {
      const engagement = this.state.engagements.get(effect.createdEngagementId);
      if (!engagement) {
        throw new Error("engagement missing during revert");
      }
      this.state.engagements.delete(engagement.engagementId);
      this.appendTimelineEvent(engagement.partitionId, {
        eventType: "engagement.created.reverted",
        subjectType: "engagement",
        subjectId: engagement.engagementId,
        details: {},
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "engagement.state-change" && effect.createdEngagementId) {
      const engagement = this.state.engagements.get(effect.createdEngagementId);
      if (!engagement) {
        throw new Error("engagement missing during revert");
      }
      if (!effect.priorEngagementState) {
        throw new Error("missing prior engagement state for revert");
      }
      engagement.state = effect.priorEngagementState;
      engagement.updatedAt = this.now();
      this.state.engagements.set(effect.createdEngagementId, engagement);

      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "engagement.state.changed.reverted",
        subjectType: "engagement",
        subjectId: engagement.engagementId,
        details: {
          restoredState: effect.priorEngagementState,
        },
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "commitment.create" && effect.createdCommitmentId) {
      const commitment = this.state.commitments.get(effect.createdCommitmentId);
      if (!commitment) {
        throw new Error("commitment missing during revert");
      }
      if (commitment.milestoneId) {
        const milestone = this.state.milestones.get(commitment.milestoneId);
        if (milestone) {
          milestone.commitmentIds = milestone.commitmentIds.filter((entry) => entry !== effect.createdCommitmentId);
          this.state.milestones.set(milestone.milestoneId, milestone);
        }
      }
      this.state.commitments.delete(effect.createdCommitmentId);
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "commitment.created.reverted",
        subjectType: "commitment",
        subjectId: effect.createdCommitmentId,
        details: {},
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "commitment.state-change" && effect.commitmentId) {
      const commitment = this.state.commitments.get(effect.commitmentId);
      if (!commitment) {
        throw new Error("commitment missing during revert");
      }
      if (effect.commitmentStateFrom) {
        commitment.state = effect.commitmentStateFrom;
        commitment.updatedAt = this.now();
        this.state.commitments.set(effect.commitmentId, commitment);
      }
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "commitment.state.changed.reverted",
        subjectType: "commitment",
        subjectId: effect.commitmentId,
        details: {
          restoredState: effect.commitmentStateFrom,
        },
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "milestone.create" && effect.createdMilestoneId) {
      this.state.milestones.delete(effect.createdMilestoneId);
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "milestone.created.reverted",
        subjectType: "milestone",
        subjectId: effect.createdMilestoneId,
        details: {},
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "milestone.state-change" && effect.milestoneId && effect.milestoneStateFrom && effect.milestoneStateTo) {
      const milestone = this.state.milestones.get(effect.milestoneId);
      if (!milestone) {
        throw new Error("milestone missing during revert");
      }
      milestone.state = effect.milestoneStateFrom;
      milestone.updatedAt = this.now();
      this.state.milestones.set(effect.milestoneId, milestone);
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "milestone.state.changed.reverted",
        subjectType: "milestone",
        subjectId: effect.milestoneId,
        details: {
          restoredState: effect.milestoneStateFrom,
          revertedTo: effect.milestoneStateTo,
        },
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "risk.record" && effect.createdRiskId) {
      this.state.riskSignals.delete(effect.createdRiskId);
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "risk.removed",
        subjectType: "risk",
        subjectId: effect.createdRiskId,
        details: {},
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "meeting.create" && effect.createdMeetingId) {
      const meeting = this.state.meetings.get(effect.createdMeetingId);
      if (meeting) {
        for (const noteId of meeting.noteIds) {
          this.state.meetingNotes.delete(noteId);
        }
        this.state.meetings.delete(meeting.meetingId);
      }
      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "meeting.created.reverted",
        subjectType: "meeting",
        subjectId: effect.createdMeetingId,
        details: {},
        provenance: proposal.provenance,
      });
    }

    if (effect.kind === "decision.record") {
      if (effect.createdDecisionId) {
        const decision = this.state.decisions.get(effect.createdDecisionId);
        if (decision) {
          for (const commitmentId of decision.sourceCommitmentIds) {
            this.state.commitments.delete(commitmentId);
          }
          if (decision.meetingId) {
            const meeting = this.state.meetings.get(decision.meetingId);
            if (meeting) {
              const decisionIds = meeting.decisionIds.filter((entry) => entry !== decision.decisionId);
              this.state.meetings.set(decision.meetingId, {
                ...meeting,
                decisionIds,
                updatedAt: this.now(),
              });
            }
          }
          this.state.decisions.delete(effect.createdDecisionId);
        }
      }

      if (effect.decisionSupersedesDecisionId && effect.decisionStateFrom) {
        const superseded = this.state.decisions.get(effect.decisionSupersedesDecisionId);
        if (superseded) {
          superseded.status = effect.decisionStateFrom;
          superseded.supersedingDecisionId = undefined;
          superseded.updatedAt = this.now();
          this.state.decisions.set(superseded.decisionId, superseded);
        }
      }

      this.appendTimelineEvent(partitionFromInput(proposal), {
        eventType: "decision.record.reverted",
        subjectType: "decision",
        subjectId: effect.createdDecisionId || "",
        details: {
          createdDecisionId: effect.createdDecisionId,
        },
        provenance: proposal.provenance,
      });
    }

    proposal.status = "reverted";
    proposal.updatedAt = now;
    proposal.resolvedAt = now;
    proposal.resolvedBy = proposal.provenance.actorId;
    proposal.decisionNotes = "reverted by explicit operation";
    this.state.proposals.set(proposalId, proposal);
    return deepCopy(proposal);
  }

  public setEngagementState(engagementId: string, nextState: IotaEngagementState, provenance: IotaProvenance): IdentityProposal {
    const engagement = this.state.engagements.get(engagementId);
    if (!engagement) {
      throw new Error(`missing engagement: ${engagementId}`);
    }
    this.validateNonEmpty(nextState, "nextState");

    const proposal = this.newProposal("engagement.state-change", engagement.partitionId, {
      engagementId,
      nextState,
      provenance,
    });
    proposal.effect = {
      kind: "engagement.state-change",
      relationshipId: engagement.relationshipId,
      priorEngagementState: engagement.state,
      createdEngagementId: engagement.engagementId,
    };

    const previous = engagement.state;
    engagement.state = nextState;
    engagement.updatedAt = this.now();
    this.state.engagements.set(engagement.engagementId, engagement);

    proposal.status = "approved";
    proposal.updatedAt = engagement.updatedAt;
    proposal.resolvedAt = engagement.updatedAt;
    proposal.resolvedBy = provenance.actorId;
    proposal.effect.priorEngagementState = previous;
    proposal.decisionNotes = "state-change applied immediately";

    this.state.proposals.set(proposal.proposalId, proposal);
    this.appendTimelineEvent(engagement.partitionId, {
      eventType: "engagement.state.changed",
      subjectType: "engagement",
      subjectId: engagement.engagementId,
      details: {
        priorState: previous,
        nextState,
      },
      provenance,
    });

    return deepCopy(proposal);
  }

  public getIdentity(identityId: string): IotaIdentity | null {
    const identity = this.state.identities.get(identityId);
    return identity ? deepCopy(identity) : null;
  }

  public getRelationshipsForIdentity(identityId: string): IotaRelationship[] {
    return Array.from(this.state.relationships.values())
      .filter((relationship) =>
        (relationship.sourceIdentityId === identityId || relationship.targetIdentityId === identityId)
        && relationship.state !== "ended",
      )
      .map((relationship) => ({ ...relationship }));
  }

  public getEngagementsForRelationship(relationshipId: string): IotaEngagement[] {
    return Array.from(this.state.engagements.values())
      .filter((engagement) => engagement.relationshipId === relationshipId)
      .map((engagement) => ({ ...engagement }));
  }

  public getTimeline(partitionId: string, window?: IotaTimelineWindow): TimelineProjection {
    const events = this.state.timeline.get(partitionId) || [];
    const start = Date.parse(window?.after || "1970-01-01T00:00:00.000Z");
    const end = Date.parse(window?.before || "9999-12-31T23:59:59.999Z");

    const filtered = events
      .filter((event) => {
        const at = Date.parse(event.occurredAt);
        return at >= start && at <= end;
      })
      .sort(sortByOccurredAt);

    return {
      partitionId,
      events: window?.limit ? filtered.slice(0, window.limit) : filtered,
    };
  }

  public listProposals(partitionId?: string): IdentityProposal[] {
    return Array.from(this.state.proposals.values())
      .filter((proposal) => !partitionId || proposal.partitionId === partitionId)
      .sort((left, right) => {
        const compared = Date.parse(right.createdAt) - Date.parse(left.createdAt);
        return compared !== 0 ? compared : right.proposalId.localeCompare(left.proposalId);
      })
      .map((proposal) => deepCopy(proposal));
  }

  public proposalById(proposalId: string): IdentityProposal | null {
    const proposal = this.state.proposals.get(proposalId);
    return proposal ? deepCopy(proposal) : null;
  }

  private validateNonEmpty(value: string, field: string): void {
    if (!value || String(value).trim().length === 0) {
      throw new Error(`${field} is required`);
    }
  }

  private validateTimestamp(value: string, field: string): void {
    const parsed = Date.parse(value);
    if (Number.isNaN(parsed)) {
      throw new Error(`${field} is not a valid timestamp`);
    }
  }

  private newProposal(proposalType: ProposalType, partitionId: string, input: Record<string, unknown>): IdentityProposal {
    const now = this.now();
    const provenance = input.provenance as IotaProvenance | undefined;
    if (!provenance || !provenance.actorId || !provenance.actorType) {
      throw new Error("proposal provenance actorId and actorType are required");
    }

    return {
      proposalId: randomUUID(),
      partitionId,
      proposalType,
      status: "open",
      input: { ...input },
      provenance,
      createdAt: now,
      updatedAt: now,
    };
  }

  private createIdentity(
    partitionId: string,
    kind: IotaIdentityKind,
    canonicalName: string,
    aliases: readonly string[],
    provenance: IotaProvenance,
  ): IotaIdentity {
    this.validateNonEmpty(canonicalName, "canonicalName");
    const now = this.now();
    const identity: IotaIdentity = {
      identityId: randomUUID(),
      partitionId,
      kind,
      canonicalName,
      aliases: [...aliases],
      provenance,
      createdAt: now,
      updatedAt: now,
      active: true,
    };
    this.state.identities.set(identity.identityId, identity);
    return toIdentitySnapshot(identity);
  }

  private applyIdentityMerge(keptIdentityId: string, mergedIdentityId: string, provenance: IotaProvenance): IotaIdentity {
    const kept = this.state.identities.get(keptIdentityId);
    const merged = this.state.identities.get(mergedIdentityId);
    if (!kept || !merged) {
      throw new Error("identity missing for merge");
    }
    if (!kept.active) {
      throw new Error("kept identity is not active");
    }
    if (!merged.active) {
      throw new Error("merged identity is already inactive");
    }

    merged.active = false;
    merged.mergedInto = kept.identityId;
    merged.replacedBy = kept.identityId;
    merged.updatedAt = this.now();
    this.state.identities.set(mergedIdentityId, merged);
    kept.updatedAt = this.now();
    this.state.identities.set(keptIdentityId, kept);
    this.appendTimelineEvent(kept.partitionId, {
      eventType: "identity.merge.applied",
      subjectType: "identity",
      subjectId: keptIdentityId,
      details: {
        keptIdentityId,
        mergedIdentityId,
      },
      provenance,
    });
    return toIdentitySnapshot(merged);
  }

  private createRelationship(
    partitionId: string,
    sourceIdentityId: string,
    targetIdentityId: string,
    relationshipType: string,
    provenance: IotaProvenance,
  ): IotaRelationship {
    this.assertIdentityInPartition(partitionId, sourceIdentityId);
    this.assertIdentityInPartition(partitionId, targetIdentityId);

    const now = this.now();
    const relationship: IotaRelationship = {
      relationshipId: randomUUID(),
      partitionId,
      sourceIdentityId,
      targetIdentityId,
      relationshipType,
      state: "active",
      provenance,
      createdAt: now,
      updatedAt: now,
    };
    this.state.relationships.set(relationship.relationshipId, relationship);
    return toRelationshipSnapshot(relationship);
  }

  private createEngagement(
    partitionId: string,
    relationshipId: string,
    title: string,
    provenance: IotaProvenance,
  ): IotaEngagement {
    this.assertRelationshipInPartition(partitionId, relationshipId);

    const now = this.now();
    const engagement: IotaEngagement = {
      engagementId: randomUUID(),
      partitionId,
      relationshipId,
      title,
      state: "proposed",
      provenance,
      createdAt: now,
      updatedAt: now,
    };
    this.state.engagements.set(engagement.engagementId, engagement);
    return toEngagementSnapshot(engagement);
  }

  private createMeeting(
    partitionId: string,
    title: string,
    scheduledAt: string,
    participants: readonly string[],
    agenda: readonly string[],
    provenance: IotaProvenance,
  ): IotaMeeting {
    this.validateTimestamp(scheduledAt, "scheduledAt");
    if (participants.length === 0) {
      throw new Error("meeting participants are required");
    }
    const now = this.now();
    const meeting: IotaMeeting = {
      meetingId: randomUUID(),
      partitionId,
      title,
      scheduledAt,
      status: "planned",
      participants: [...participants],
      agenda: [...agenda],
      noteIds: [],
      decisionIds: [],
      provenance,
      createdAt: now,
      updatedAt: now,
    };
    this.state.meetings.set(meeting.meetingId, meeting);
    return deepCopy(meeting);
  }

  private createDecisionAndTasks(
    partitionId: string,
    provenance: IotaProvenance,
    input: {
      meetingId?: string;
      title: string;
      rationale: string;
      alternatives: readonly IotaDecisionAlternative[];
      selectedAlternativeIndex?: number;
      participants: readonly string[];
      evidence: readonly string[];
      supersedesDecisionId?: string;
      actions: readonly IotaDecisionActionInput[];
    },
    ): {
    decision: IotaDecision;
    commitmentIds: readonly string[];
    supersededDecision?: IotaDecision;
    supersededDecisionPreviousState?: IotaDecisionState;
  } {
    if (input.meetingId) {
      const meeting = this.state.meetings.get(input.meetingId);
      if (!meeting) {
        throw new Error(`missing meeting: ${input.meetingId}`);
      }
      if (meeting.partitionId !== partitionId) {
        throw new Error("partition leak: meeting decision mismatch");
      }
    }
    for (const evidenceItem of input.evidence) {
      this.validateNonEmpty(evidenceItem, "evidence");
    }

    const decisionId = randomUUID();
    const now = this.now();
    const createdCommitmentIds: string[] = [];
    let snapshotDecision: IotaDecision | null = null;
    let supersededDecisionPreviousState: IotaDecisionState | undefined;
    const decision: IotaDecision = {
      decisionId,
      partitionId,
      meetingId: input.meetingId,
      title: input.title,
      rationale: input.rationale,
      alternatives: [...input.alternatives],
      selectedAlternativeIndex: input.selectedAlternativeIndex,
      participants: [...input.participants],
      evidence: [...input.evidence],
      status: "adopted",
      sourceCommitmentIds: [],
      supersedesDecisionId: input.supersedesDecisionId,
      provenance,
      createdAt: now,
      updatedAt: now,
    };

    if (input.supersedesDecisionId) {
      const toSupersede = this.state.decisions.get(input.supersedesDecisionId);
      if (!toSupersede) {
        throw new Error(`missing decision to supersede: ${input.supersedesDecisionId}`);
      }
      if (toSupersede.partitionId !== partitionId) {
        throw new Error("partition leak: decision supersession mismatch");
      }
      if (toSupersede.status === "closed") {
        throw new Error("cannot supersede closed decision");
      }
      supersededDecisionPreviousState = toSupersede.status;
      snapshotDecision = deepCopy(toSupersede);
      toSupersede.status = "superseded";
      toSupersede.supersedingDecisionId = decisionId;
      toSupersede.updatedAt = now;
      this.state.decisions.set(toSupersede.decisionId, toSupersede);
    }

    this.state.decisions.set(decisionId, decision);
    const rollbackOnFailure: string[] = [];
    try {
      for (const action of input.actions) {
        const commitment = this.createCommitment(
          partitionId,
          action.title,
          action.assigneeId,
          action.dueAt,
          action.waitingOn || [],
          action.engagementId,
          action.milestoneId,
          action.riskLevel || "low",
          provenance,
        );
        const updated = { ...commitment, sourceDecisionIds: [decisionId] };
        this.state.commitments.set(updated.commitmentId, updated);
        rollbackOnFailure.push(updated.commitmentId);
        createdCommitmentIds.push(updated.commitmentId);
      }
    } catch (error) {
      for (const id of rollbackOnFailure) {
        this.state.commitments.delete(id);
      }
      this.state.decisions.delete(decisionId);
      if (snapshotDecision) {
        this.state.decisions.set(snapshotDecision.decisionId, snapshotDecision);
      }
      throw error;
    }

    const completedDecision = {
      ...decision,
      sourceCommitmentIds: [...createdCommitmentIds],
      status: decision.status,
      updatedAt: this.now(),
    };
    this.state.decisions.set(decisionId, completedDecision);

    if (input.meetingId) {
      const meeting = this.state.meetings.get(input.meetingId);
      if (!meeting) {
        throw new Error(`missing meeting: ${input.meetingId}`);
      }
      this.state.meetings.set(input.meetingId, {
        ...meeting,
        decisionIds: [...meeting.decisionIds, completedDecision.decisionId],
        updatedAt: this.now(),
      });
    }

    return {
      decision: deepCopy(completedDecision),
      commitmentIds: [...createdCommitmentIds],
      supersededDecision: snapshotDecision ? deepCopy(snapshotDecision) : undefined,
      supersededDecisionPreviousState,
    };
  }

  private createCommitment(
    partitionId: string,
    title: string,
    assigneeId: string,
    dueAt: string,
    waitingOn: readonly string[],
    engagementId: string | undefined,
    milestoneId: string | undefined,
    riskLevel: IotaRiskLevel,
    provenance: IotaProvenance,
  ): IotaCommitment {
    this.validateNonEmpty(partitionId, "partitionId");
    this.validateNonEmpty(title, "title");
    this.validateNonEmpty(assigneeId, "assigneeId");
    this.validateTimestamp(dueAt, "dueAt");
    this.assertNoCrossPartitionWaiting(partitionId, waitingOn);
    if (engagementId) {
      this.assertEngagementInPartition(partitionId, engagementId);
    }
    if (milestoneId) {
      const milestone = this.state.milestones.get(milestoneId);
      if (!milestone) {
        throw new Error(`milestone missing: ${milestoneId}`);
      }
      if (milestone.partitionId !== partitionId) {
        throw new Error("partition leak: milestone cross-partition");
      }
    }

    const now = this.now();
    const commitment: IotaCommitment = {
      commitmentId: randomUUID(),
      partitionId,
      engagementId,
      milestoneId,
      title,
      assigneeId,
      dueAt,
      waitingOn: [...waitingOn],
      state: "open",
      provenance,
      riskLevel,
      reopenedCount: 0,
      sourceDecisionIds: [],
      createdAt: now,
      updatedAt: now,
    };
    this.state.commitments.set(commitment.commitmentId, commitment);
    return deepCopy(commitment);
  }

  private createMilestone(
    partitionId: string,
    title: string,
    dueAt: string | undefined,
    provenance: IotaProvenance,
  ): IotaMilestone {
    if (dueAt) {
      this.validateTimestamp(dueAt, "dueAt");
    }
    const now = this.now();
    const milestone: IotaMilestone = {
      milestoneId: randomUUID(),
      partitionId,
      title,
      dueAt,
      state: "planned",
      commitmentIds: [],
      provenance,
      createdAt: now,
      updatedAt: now,
    };
    this.state.milestones.set(milestone.milestoneId, milestone);
    return deepCopy(milestone);
  }

  private createRiskSignal(
    partitionId: string,
    subjectType: IotaReviewSubject,
    subjectId: string,
    level: IotaRiskLevel,
    rationale: string,
    provenance: IotaProvenance,
  ): IotaRiskSignal {
    const risk: IotaRiskSignal = {
      riskId: randomUUID(),
      partitionId,
      subjectType,
      subjectId,
      level,
      rationale,
      observedAt: this.now(),
    };
    this.state.riskSignals.set(risk.riskId, risk);
    return deepCopy(risk);
  }

  private linkCommitmentToMilestone(commitmentId: string, milestoneId: string): void {
    const milestone = this.state.milestones.get(milestoneId);
    if (!milestone) {
      throw new Error(`milestone missing: ${milestoneId}`);
    }
    const commitment = this.state.commitments.get(commitmentId);
    if (!commitment) {
      throw new Error(`commitment missing: ${commitmentId}`);
    }
    if (milestone.partitionId !== commitment.partitionId) {
      throw new Error("partition leak: milestone commitment mismatch");
    }
    const current = new Set(milestone.commitmentIds);
    current.add(commitmentId);
    milestone.commitmentIds = Array.from(current);
    this.state.milestones.set(milestoneId, milestone);
  }

  private applyCommitmentTransition(
    commitment: IotaCommitment,
    nextState: IotaCommitmentState,
    provenance: IotaProvenance,
    rationale?: string,
    assigneeId?: string,
    dueAt?: string,
    waitingOn?: readonly string[],
  ): void {
    this.validateCommitmentTransition(commitment.state, nextState);
    if (assigneeId) {
      commitment.assigneeId = assigneeId;
    }
    if (dueAt) {
      this.validateTimestamp(dueAt, "dueAt");
      commitment.dueAt = dueAt;
    }
    if (waitingOn) {
      this.assertNoCrossPartitionWaiting(commitment.partitionId, waitingOn);
      commitment.waitingOn = [...waitingOn];
    }

    const now = this.now();
    commitment.updatedAt = now;
    commitment.state = nextState;
    if (nextState === "complete") {
      commitment.completedAt = now;
    } else if (nextState === "cancelled") {
      commitment.cancelledAt = now;
    } else if (nextState === "reopened") {
      commitment.reopenedCount += 1;
    }
    this.state.commitments.set(commitment.commitmentId, deepCopy(commitment));
  }

  private applyMilestoneTransition(milestone: IotaMilestone, nextState: IotaMilestoneState): void {
    this.validateMilestoneTransition(milestone.state, nextState);
    const now = this.now();
    milestone.state = nextState;
    milestone.updatedAt = now;
    this.state.milestones.set(milestone.milestoneId, deepCopy(milestone));
  }

  private createReviewRequestFromProposal(
    partitionId: string,
    details: {
      reviewSubjectType: IotaReviewSubject;
      reviewSubjectId: string;
      reason: string;
    },
    actor: IotaProvenance,
  ): string {
    const item: IotaReviewQueueItem = {
      reviewId: randomUUID(),
      partitionId,
      subjectType: details.reviewSubjectType,
      subjectId: details.reviewSubjectId,
      reason: details.reason,
      status: "open",
      requestedBy: actor.actorId,
      requestedAt: this.now(),
    };
    this.state.reviewQueue.set(item.reviewId, item);
    return item.reviewId;
  }

  private validateCommitmentTransition(current: IotaCommitmentState, next: IotaCommitmentState): void {
    if (current === next) {
      return;
    }
    if (current === "complete" && next !== "reopened") {
      throw new Error(`invalid commitment transition ${current} -> ${next}`);
    }
    if (current === "cancelled" && next !== "reopened") {
      throw new Error(`invalid commitment transition ${current} -> ${next}`);
    }
    if (current === "reopened" && next === "open") {
      throw new Error(`invalid commitment transition ${current} -> ${next}`);
    }
  }

  private validateMilestoneTransition(current: IotaMilestoneState, next: IotaMilestoneState): void {
    if (current === next) {
      return;
    }
    if (current === "complete" && next !== "active" && next !== "planned") {
      throw new Error(`invalid milestone transition ${current} -> ${next}`);
    }
  }

  private isActiveTask(state: IotaCommitmentState): boolean {
    return state !== "complete" && state !== "cancelled";
  }

  private commitmentPriorityState(state: IotaCommitmentState): number {
    if (state === "waiting") {
      return 1;
    }
    if (state === "blocked") {
      return 2;
    }
    if (state === "open") {
      return 3;
    }
    if (state === "reopened") {
      return 4;
    }
    return 5;
  }

  private requireProposal(proposalId: string): IdentityProposal {
    const proposal = this.state.proposals.get(proposalId);
    if (!proposal) {
      throw new Error(`proposal missing: ${proposalId}`);
    }
    return proposal;
  }

  private getRelationship(relationshipId: string): IotaRelationship {
    const relationship = this.state.relationships.get(relationshipId);
    if (!relationship) {
      throw new Error(`missing relationship: ${relationshipId}`);
    }
    return relationship;
  }

  private appendTimelineEvent(partitionId: string, event: Omit<IotaTimelineEvent, "partitionId" | "eventId" | "occurredAt">): void {
    const occurredAt = this.now();
    const bucket = this.state.timeline.get(partitionId) || [];
    const timelineEvent: IotaTimelineEvent = {
      eventId: randomUUID(),
      partitionId,
      occurredAt,
      ...event,
      actorId: event.actorId || event.provenance.actorId,
    };
    bucket.push(timelineEvent);
    bucket.sort(sortByOccurredAt);
    this.state.timeline.set(partitionId, bucket);
  }

  private assertIdentityInPartition(partitionId: string, identityId: string): void {
    const identity = this.state.identities.get(identityId);
    if (!identity) {
      throw new Error(`identity missing: ${identityId}`);
    }
    if (identity.partitionId !== partitionId) {
      throw new Error("partition leak: cross-partition identity reference");
    }
  }

  private assertRelationshipInPartition(partitionId: string, relationshipId: string): void {
    const relationship = this.state.relationships.get(relationshipId);
    if (!relationship) {
      throw new Error(`relationship missing: ${relationshipId}`);
    }
    if (relationship.partitionId !== partitionId) {
      throw new Error("partition leak: cross-partition relationship reference");
    }
  }

  private assertEngagementInPartition(partitionId: string, engagementId: string): void {
    const engagement = this.state.engagements.get(engagementId);
    if (!engagement) {
      throw new Error(`missing engagement: ${engagementId}`);
    }
    if (engagement.partitionId !== partitionId) {
      throw new Error("partition leak: cross-partition engagement reference");
    }
  }

  private assertNoCrossPartitionWaiting(partitionId: string, waitingOn?: readonly string[]): void {
    for (const commitmentId of waitingOn || []) {
      const dependency = this.state.commitments.get(commitmentId);
      if (!dependency) {
        throw new Error(`missing waiting task: ${commitmentId}`);
      }
      if (dependency.partitionId !== partitionId) {
        throw new Error("partition leak: waiting task cross-partition");
      }
    }
  }

  private assertDifferentIdentityRefs(leftId: string, rightId: string): void {
    if (leftId === rightId) {
      throw new Error("relationship participants must be distinct");
    }
  }

  private assertSamePartition(partitionId: string, ...entityIds: string[]): void {
    for (const entityId of entityIds) {
      const entity = this.state.identities.get(entityId);
      if (!entity) {
        throw new Error(`identity missing: ${entityId}`);
      }
      if (entity.partitionId !== partitionId) {
        throw new Error("partition leak: proposal references identity across partition");
      }
    }
  }
}

function partitionFromInput(entity: { partitionId: string }): string {
  return entity.partitionId;
}

export function buildIdentityFingerprint(identity: IotaIdentity): string {
  return stableStringify({
    identityId: identity.identityId,
    partitionId: identity.partitionId,
    kind: identity.kind,
    canonicalName: identity.canonicalName,
    aliases: identity.aliases,
    mergedInto: identity.mergedInto,
    replacedBy: identity.replacedBy,
    active: identity.active,
  });
}
