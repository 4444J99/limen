import InsightsClient from "./insights-client";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Insights",
  description: "Aggregate view of fleet insights, censor signals, and lineage corrections.",
};

export default function InsightsPage() {
  return <InsightsClient />;
}
