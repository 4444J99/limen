import AuthenticatedDashboard from "../authenticated-dashboard";

export const dynamic = "force-static";

export default function InternalSurface() {
  return <AuthenticatedDashboard apiUrl={process.env.NEXT_PUBLIC_API_URL || ""} />;
}
