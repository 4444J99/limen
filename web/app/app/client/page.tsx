import ClientSurfaceClient from "./client-surface-client";

export const dynamic = "force-static";

export default function ClientSurface() {
  return <ClientSurfaceClient apiUrl={process.env.NEXT_PUBLIC_API_URL || ""} />;
}
