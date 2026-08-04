import MarketplaceClient from "./marketplace-client";
import type { Metadata } from "next";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Marketplace",
  description: "Browse agent integrations, inspect capabilities, install apps, and submit tasks.",
};

export default function MarketplacePage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
  return <MarketplaceClient apiUrl={apiUrl} />;
}
