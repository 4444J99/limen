import QASurfaceClient from "./qa-surface-client";

export const dynamic = "force-static";

export default function QASurface() {
  return <QASurfaceClient apiUrl={process.env.NEXT_PUBLIC_API_URL || ""} />;
}
