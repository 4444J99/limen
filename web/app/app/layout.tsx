import "./globals.css";

export const metadata = {
  title: "Limen | Universal Task Intake",
  description: "Operational dashboard for cross-agent task dispatch and PR health.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
