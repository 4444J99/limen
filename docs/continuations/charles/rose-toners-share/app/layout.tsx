import type { Metadata } from "next";
import { Cormorant_Garamond, Manrope } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";

const display = Cormorant_Garamond({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
});

const sans = Manrope({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host =
    requestHeaders.get("x-forwarded-host") ??
    requestHeaders.get("host") ??
    "localhost:3000";
  const protocol =
    requestHeaders.get("x-forwarded-proto") ??
    (host.startsWith("localhost") ? "http" : "https");
  const origin = `${protocol}://${host}`;
  const title = "Downs Style Studio | Archive & Voice";
  const socialTitle = "Downs Style Studio";
  const description =
    "The complete 258-post Downs Style archive, Charles Downs's evidence-backed voice system, and a working editorial studio for what comes next.";
  const socialImage = `${origin}/og-archive.png`;

  return {
    metadataBase: new URL(origin),
    title,
    description,
    robots: {
      index: false,
      follow: false,
    },
    openGraph: {
      title: socialTitle,
      description,
      type: "website",
      images: [
        {
          url: socialImage,
          width: 1672,
          height: 941,
          alt: "Downs Style Studio archive and voice system",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: socialTitle,
      description,
      images: [socialImage],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${sans.variable}`}>{children}</body>
    </html>
  );
}
