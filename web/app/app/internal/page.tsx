import AuthenticatedDashboard from "../authenticated-dashboard";
import type { Metadata } from "next";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Internal",
  description: "Owner internal board showing full task queue, lifecycle gates, and fleet health.",
};

export default function InternalSurface() {
  return <AuthenticatedDashboard apiUrl={process.env.NEXT_PUBLIC_API_URL || ""} />;
}
