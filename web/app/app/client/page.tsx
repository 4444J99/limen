import ClientSurfaceClient from "./client-surface-client";
import type { Metadata } from "next";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Client",
  description: "Client surface exposing delivery gate status and lifecycle summary.",
};

export default function ClientSurface() {
  return <ClientSurfaceClient apiUrl={process.env.NEXT_PUBLIC_API_URL || ""} />;
}
