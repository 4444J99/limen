export type InboxPartition = "inbox" | "entities" | "tasks" | "decisions" | "links" | "archive" | "quarantine";
export type InboxSourceType = "note" | "url" | "file" | "source_ref";

export interface InboxRecord {
  id: string;
  title: string;
  source_type: InboxSourceType;
  source_reference: string;
  body_excerpt: string;
  partition: InboxPartition;
  captured_at: string;
  captured_by: string;
  policy_consequences: string[];
  provenance: {
    source_system: string;
    source_reference: string;
    observed_at: string;
    policy_vector: string[];
    source_note: string;
  };
}

export interface InboxStatusData {
  status: "ok" | "missing";
  surface: "inbox";
  generated_at: string;
  generated_by?: string;
  total_records: number;
  partitions: Record<InboxPartition, number>;
  records: InboxRecord[];
}
