import type { Metadata } from "next";
import { SiteHeader } from "../site-header";
import voiceMetrics from "../../../downs-style-voice-metrics.json";

const baselineMetrics = voiceMetrics.baseline.metrics;
const voiceHeadline = {
  words: baselineMetrics.words.toLocaleString("en-US"),
  firstPerson: baselineMetrics.pronouns.first_person_singular.per_1000_words,
  firstPersonPlural: baselineMetrics.pronouns.first_person_plural.per_1000_words,
  love: baselineMetrics.phrase_markers["i love"].count,
} as const;

export const metadata: Metadata = {
  title: "Charles's voice system | Downs Style Studio",
  description:
    "An evidence-backed voice system derived from Charles Downs's complete public archive, with writing moves, guardrails, and channel-ready guidance.",
  openGraph: {
    title: "Charles's voice was already there",
    description:
      "The complete Downs Style archive, assembled into a durable Natural Center and practical editorial profile.",
    images: [
      {
        url: "/og-archive.png",
        width: 1672,
        height: 941,
        alt: "Downs Style Studio archive and voice system",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    images: ["/og-archive.png"],
  },
};

const naturalCenter = [
  {
    number: "01",
    title: "Thematic core",
    copy: "Luxury becomes believable when Charles meets it in a real ritual: a candle at home, a product on skin, or a piece of clothing in motion.",
  },
  {
    number: "02",
    title: "Aesthetic signature",
    copy: "Warm, intimate, sensory, and aspirational without becoming remote. High-low comparisons keep beautiful things connected to ordinary life.",
  },
  {
    number: "03",
    title: "Tonal vector",
    copy: "Personal discovery moves into genuine excitement, then an honest qualification, and finally a clear verdict.",
  },
  {
    number: "04",
    title: "Narrative bias",
    copy: "Experience leads. Charles notices something, tries it, describes what changed, checks the downside, and decides whether it earns a place.",
  },
  {
    number: "05",
    title: "Symbolic markers",
    copy: "Favorites, rituals, seasons, texture, scent, glow, comfort, and the small ceremony of making an everyday step feel special.",
  },
  {
    number: "06",
    title: "Negative space",
    copy: "No catalogue voice, clinical omniscience, anonymous brand copy, invented results, or enthusiasm that never admits a drawback.",
  },
  {
    number: "07",
    title: "Brand embedding",
    copy: "Downs Style is a personal point of view before it is a publication. Write from I by default; use we only when the team is truly speaking.",
  },
];

const writingMoves = [
  ["Notice", "Begin with the encounter: where it appeared, who mentioned it, or why this particular moment made it matter."],
  ["Try", "Put Charles in the scene. The reader should understand the ritual before receiving the conclusion."],
  ["Feel", "Name texture, scent, fit, mood, or atmosphere in plain language before reaching for technical detail."],
  ["Qualify", "Let however, although, or an intimate aside complicate the excitement. The drawback is part of the personality."],
  ["Decide", "End with a preference, rating, recommendation, or shop cue. Charles does not disappear before the verdict."],
] as const;

const runway = [
  {
    number: "01",
    title: "How to properly let a candle burn",
    copy: "A practical ritual story: first burn, wick care, tunneling, scent throw, and the common mistakes that waste a beautiful candle.",
  },
  {
    number: "02",
    title: "Transcend Cosmetics becomes Transcend Essentials",
    copy: "A rebrand story about the name changing because the world around the product became larger than cosmetics.",
  },
  {
    number: "03",
    title: "The summer fabric sequence",
    copy: "Cotton first, silk second, then a head-to-head piece asking which fabric wins each garment and part of the body.",
  },
];

export default function VoicePage() {
  return (
    <main className="voice-page">
      <SiteHeader active="voice" />

      <section className="voice-hero">
        <div>
          <p className="kicker">The Charles Downs Natural Center</p>
          <h1>
            His voice was
            <em>already there.</em>
          </h1>
        </div>
        <div className="voice-hero-note">
          <p>
            We did not invent a persona. We read the full public record,
            separated Charles&apos;s durable instincts from changing blog formats,
            and assembled the pattern into a system future posts can actually
            use.
          </p>
          <span>257-post causal baseline · 2017—2024</span>
        </div>
      </section>

      <section className="voice-metrics" aria-label="Headline voice evidence">
        <article>
          <strong>{voiceHeadline.words}</strong>
          <span>alphabetic tokens in the historical baseline</span>
        </article>
        <article>
          <strong>{voiceHeadline.firstPerson}</strong>
          <span>I / me / my / mine uses per 1,000 words</span>
        </article>
        <article>
          <strong>{voiceHeadline.firstPersonPlural}</strong>
          <span>we / us / our uses per 1,000 words</span>
        </article>
        <article>
          <strong>{voiceHeadline.love}×</strong>
          <span>“I love” across the archive baseline</span>
        </article>
      </section>

      <section className="voice-proof">
        <div className="voice-proof-heading">
          <p className="kicker">The clearest finding</p>
          <h2>I is the fingerprint.</h2>
        </div>
        <div className="voice-proof-copy">
          <p>
            Charles&apos;s historical voice is not an anonymous editorial we. His
            first-person singular language appears roughly forty-six times as
            often as the plural form.
          </p>
          <p>
            That matters. The reader returns for a person making a choice in
            public—“my favorite,” “I have to say,” “overall I”—not a brand
            smoothing every reaction into consensus.
          </p>
        </div>
      </section>

      <section className="voice-system" id="natural-center">
        <div className="section-intro">
          <p className="kicker">The assembled center</p>
          <h2>Seven parts. One recognizable point of view.</h2>
          <p>
            The Natural Center holds what stays true even as the subject shifts
            from a face mask to a candle, a hotel, or a cotton shirt.
          </p>
        </div>
        <div className="voice-system-grid">
          {naturalCenter.map((item) => (
            <article key={item.number}>
              <span>{item.number}</span>
              <h3>{item.title}</h3>
              <p>{item.copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="voice-architecture" aria-labelledby="architecture-title">
        <div className="section-intro">
          <p className="kicker">The architecture</p>
          <h2 id="architecture-title">Evidence in. Charles out.</h2>
        </div>
        <div className="architecture-flow">
          <article>
            <span>01 · Corpus</span>
            <strong>258 public posts</strong>
            <p>Titles, dates, categories, structure, cadence, and recurring language.</p>
          </article>
          <i aria-hidden="true">→</i>
          <article>
            <span>02 · Natural Center</span>
            <strong>Durable identity</strong>
            <p>The themes, tone, movement, symbols, limits, and brand relationship that persist.</p>
          </article>
          <i aria-hidden="true">→</i>
          <article>
            <span>03 · Channel profile</span>
            <strong>Usable rules</strong>
            <p>Paragraph shape, point of view, editorial moves, myth checks, and platform-specific delivery.</p>
          </article>
        </div>
      </section>

      <section className="voice-movement">
        <div className="section-intro">
          <p className="kicker">The sentence-to-sentence movement</p>
          <h2>Excitement earns trust when it checks itself.</h2>
        </div>
        <ol>
          {writingMoves.map(([title, copy], index) => (
            <li key={title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h3>{title}</h3>
              <p>{copy}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="voice-guardrails">
        <div>
          <p className="kicker">Keep</p>
          <h2>The reaction.</h2>
          <ul>
            <li>Personal discovery and specific use context</li>
            <li>Enthusiasm before an honest drawback</li>
            <li>Plain sensory language and accessible luxury</li>
            <li>Single-thought paragraphs with a decisive ending</li>
          </ul>
        </div>
        <div>
          <p className="kicker">Remove</p>
          <h2>The residue.</h2>
          <ul>
            <li>Typos, run-ons, and repeated filler</li>
            <li>Copied brand language and ingredient catalogues</li>
            <li>Medical promises or universal suitability claims</li>
            <li>Generic SEO structure mistaken for Charles&apos;s voice</li>
          </ul>
        </div>
      </section>

      <section className="editorial-runway">
        <div className="section-intro">
          <p className="kicker">What this system writes next</p>
          <h2>Three ideas. One connected summer sequence.</h2>
          <p>
            Each section gets a compact myth check beside the main story: name
            the common error, explain why it persists, and replace it with one
            useful decision.
          </p>
        </div>
        <div className="runway-grid">
          {runway.map((item) => (
            <article key={item.number}>
              <span>{item.number}</span>
              <h3>{item.title}</h3>
              <p>{item.copy}</p>
            </article>
          ))}
        </div>
      </section>

      <footer>
        <div>
          <span className="footer-mark">DS</span>
          <p>
            Voice system derived from Charles&apos;s public work.
            <br />
            Evidence guides the style; it does not replace judgment.
          </p>
        </div>
        <a href="/archive">
          Search the source archive <span aria-hidden="true">↗</span>
        </a>
      </footer>
    </main>
  );
}
