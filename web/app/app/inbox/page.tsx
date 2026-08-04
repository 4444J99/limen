import InboxSurfaceClient from "./inbox-surface-client";
import { getInboxStatusData } from "../lib/data";
import type { Metadata } from "next";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Inbox",
  description: "Owner inbox for capture, policy-aware classification, and routing to explicit partitions.",
};

export default function InboxPage() {
  return <InboxSurfaceClient initialStatus={getInboxStatusData()} />;
}
