type SurfaceKey = "internal" | "client" | "public" | "qa";
type Persona = "owner" | "client" | "public";

export default function SurfaceNav({ active, persona = "owner" }: { active: SurfaceKey; persona?: Persona }) {
  const items: { key: SurfaceKey; label: string; href: string; personas: Persona[] }[] = [
    { key: "internal", label: "Internal", href: "/", personas: ["owner"] },
    { key: "qa", label: "QA", href: "/qa", personas: ["owner"] },
    { key: "client", label: "Client", href: "/client", personas: ["owner", "client"] },
    { key: "public", label: "Public", href: "/public", personas: ["owner", "client", "public"] },
  ];
  const visibleItems = items.filter((item) => item.personas.includes(persona));

  return (
    <nav className="surfaceNav" aria-label="Limen surfaces">
      {visibleItems.map((item) => (
        <a key={item.key} className={active === item.key ? "active" : ""} href={item.href}>
          {item.label}
        </a>
      ))}
    </nav>
  );
}
