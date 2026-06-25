import InsightsClient from "./insights-client";

export const metadata = {
  title: "Insights | Limen",
  description: "Aggregate view of fleet insights and signals.",
};

export default function InsightsPage() {
  return <InsightsClient />;
}
