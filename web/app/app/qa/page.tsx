import QASurfaceClient from "./qa-surface-client";
import type { Metadata } from "next";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "QA",
  description: "Owner QA surface for task verification, assignment, recovery, and archival.",
};

export default function QASurface() {
  return <QASurfaceClient apiUrl={process.env.NEXT_PUBLIC_API_URL || ""} />;
}
