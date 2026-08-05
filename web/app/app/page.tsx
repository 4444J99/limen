import PublicSurface from "./public-surface";
import type { Metadata } from "next";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Public Status",
  description: "Public-facing status page showing Limen task intake health and run plan.",
};

export default function Home() {
  return <PublicSurface />;
}
