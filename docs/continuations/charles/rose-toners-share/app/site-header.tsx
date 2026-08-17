import Link from "next/link";

type StudioSection = "article" | "archive" | "voice" | "compare";

const navigation: Array<{
  href: string;
  label: string;
  section: StudioSection;
}> = [
  { href: "/", label: "Article", section: "article" },
  { href: "/archive", label: "All 258 posts", section: "archive" },
  { href: "/voice", label: "Voice system", section: "voice" },
  { href: "/compare", label: "Compare drafts", section: "compare" },
];

export function SiteHeader({ active }: { active: StudioSection }) {
  return (
    <header className="site-header">
      <Link className="wordmark" href="/" aria-label="Downs Style Studio home">
        <span>DS</span>
        <strong>Downs Style Studio</strong>
      </Link>
      <nav aria-label="Studio navigation">
        {navigation.map((item) => (
          <Link
            href={item.href}
            key={item.section}
            aria-current={active === item.section ? "page" : undefined}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
