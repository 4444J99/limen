import PublicSurfaceContent from "../public-surface";
import type { Metadata } from "next";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Public",
  description: "Public task intake status — unrecorded capacity, run plan, and PR health.",
};

export default function PublicSurface() {
  return <PublicSurfaceContent />;
}
