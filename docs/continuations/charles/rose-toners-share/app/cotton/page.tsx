/* eslint-disable @next/next/no-img-element */
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Is Cotton Good for Summer? What the Label Leaves Out | Downs Style",
  description:
    "Is cotton good for summer? Charles Downs explains how jersey, piqué, poplin, seersucker, twill, and denim change what 100% cotton feels like.",
  robots: {
    index: false,
    follow: false,
  },
  openGraph: {
    title: "Is Cotton Good for Summer? What the Label Leaves Out",
    description:
      "Two garments can both say 100% cotton and feel completely different by noon. Here is what the label leaves out.",
    type: "article",
    images: [
      {
        url: "/cotton/hero-trousers.webp",
        width: 1600,
        height: 2400,
        alt: "Man in a relaxed shirt and pleated trousers standing in a field",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    images: ["/cotton/hero-trousers.webp"],
  },
};

const labelCards = [
  {
    name: "Jersey",
    role: "The easy knit",
    note: "Soft and flexible, but available in weights that range from light T-shirt fabric to something much denser.",
  },
  {
    name: "Piqué",
    role: "The textured knit",
    note: "More surface and structure than a basic jersey. The polo may look finished, but the actual weight still matters.",
  },
  {
    name: "Poplin + chambray",
    role: "The crisp wovens",
    note: "Clean and light when the cloth and cut cooperate. They do not have the same natural give as jersey.",
  },
  {
    name: "Twill + denim",
    role: "The structured wovens",
    note: "Useful for trousers because they hold a line. That same substance can become too much in hot weather.",
  },
] as const;

const shoppingTest = [
  ["Pick it up", "Weight usually tells me more than the cotton percentage."],
  ["Pinch the cloth", "Thickness and density are easier to feel than to read online."],
  ["Look inside", "A lining can turn one light fabric into two complete layers."],
  ["Move in it", "Room through the shoulder, body, and leg changes the entire experience."],
  ["Read past cotton", "Look for the knit or weave, care instructions, and any blend."],
] as const;

const faqs = [
  {
    question: "Is 100-percent cotton always good for summer?",
    answer:
      "No. The fiber percentage does not tell you the fabric construction, weight, lining, or cut. A light cotton jersey and rigid cotton denim can carry the same percentage while feeling completely different.",
  },
  {
    question: "Which cotton fabric is best for hot weather?",
    answer:
      "There is no single winner. Lightweight jersey, relaxed poplin or chambray, and unlined seersucker can all make sense. The finished garment still has to be light enough and cut with enough room for the day.",
  },
  {
    question: "Does cotton dry quickly?",
    answer:
      "Absorbent does not automatically mean quick-drying. Ordinary cotton can hold moisture. When drying speed is the main job, look for a garment specifically engineered and tested for moisture management.",
  },
  {
    question: "Is cotton better than linen for summer?",
    answer:
      "The useful comparison is garment against garment, not fiber name against fiber name. A light, relaxed cotton shirt may work better than a lined or heavy linen piece, while a good linen shirt may feel easier than dense cotton twill.",
  },
] as const;

const sources = [
  [
    "Cotton varieties explained",
    "https://cottonworks.com/fiber/fiber-science/cotton-varieties-explained/",
  ],
  ["Knit basics", "https://cottonworks.com/learning-hub/knitting/knit-basics/"],
  [
    "Single and double knits",
    "https://cottonworks.com/learning-hub/knitting/single-and-double-knits/",
  ],
  [
    "Basic woven fabric designs",
    "https://cottonworks.com/learning-hub/weaving/basic-woven-fabric-designs/",
  ],
  ["Denim basics", "https://cottonworks.com/learning-hub/denim/denim-basics/"],
  ["Supima FAQ", "https://supima.com/faq/"],
  [
    "University of Tennessee textile guide",
    "https://utia.tennessee.edu/publications/wp-content/uploads/sites/269/2023/10/W881.pdf",
  ],
] as const;

const articleSchema = {
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  headline: "Is Cotton Good for Summer? What the Label Leaves Out",
  description:
    "A first-person guide to how jersey, piqué, poplin, seersucker, twill, and denim change the summer cotton experience.",
  author: {
    "@type": "Person",
    name: "Charles Downs",
  },
  publisher: {
    "@type": "Organization",
    name: "Downs Style",
    url: "https://www.downsstyle.com/",
  },
  url: "https://downs-style-rose-toners-preview.ajpadavano.chatgpt.site/cotton",
  dateModified: "2026-08-03",
  image: [
    "https://downs-style-rose-toners-preview.ajpadavano.chatgpt.site/cotton/hero-trousers.webp",
    "https://downs-style-rose-toners-preview.ajpadavano.chatgpt.site/cotton/cotton-top.webp",
    "https://downs-style-rose-toners-preview.ajpadavano.chatgpt.site/cotton/cotton-bottom.webp",
  ],
  isAccessibleForFree: true,
};

function ShotNote({ children }: { children: React.ReactNode }) {
  return <span className="cotton-shot-note">{children}</span>;
}

function CottonHeader() {
  return (
    <header className="cotton-header">
      <a className="cotton-wordmark" href="#top" aria-label="Back to the top">
        <span>DS</span>
        <strong>Downs Style · Cotton review</strong>
      </a>
      <nav aria-label="Cotton article sections">
        <a href="#tops">Tops</a>
        <a href="#bottoms">Bottoms</a>
        <a href="#label-test">The label test</a>
      </nav>
    </header>
  );
}

export default function CottonPage() {
  return (
    <main className="cotton-page" id="top">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(articleSchema).replace(/</g, "\\u003c"),
        }}
      />

      <CottonHeader />

      <section className="cotton-hero" aria-labelledby="cotton-title">
        <div className="cotton-hero-copy">
          <p className="cotton-kicker">Look Book · Summer fabrics · Draft for Charles</p>
          <h1 id="cotton-title">
            Is cotton actually{" "}
            <em>good for summer?</em>
          </h1>
          <p className="cotton-dek">
            A T-shirt can feel easy until sunset while a pair of jeans becomes
            unbearable by noon. Both can say 100% cotton. Here is what the
            label leaves out.
          </p>
          <div className="cotton-hero-meta">
            <a href="#story">Read the draft</a>
            <span>By Charles Downs</span>
            <span>8 minute read</span>
          </div>
        </div>

        <div className="cotton-hero-art" aria-label="Stock photography references for Charles to recreate">
          <figure className="cotton-hero-main">
            <img
              src="/cotton/hero-trousers.webp"
              alt="Man wearing a relaxed blue shirt and pleated beige trousers outdoors"
              width="1200"
              height="1800"
              fetchPriority="high"
              decoding="async"
            />
            <ShotNote>Shot 01 · relaxed shirt + trouser silhouette</ShotNote>
          </figure>
          <figure className="cotton-hero-detail">
            <img
              src="/cotton/hero-detail.webp"
              alt="Close view of striped shirt fabric, placket, and buttons"
              width="1200"
              height="800"
              decoding="async"
            />
            <ShotNote>Shot 02 · show the weave up close</ShotNote>
          </figure>
          <span className="cotton-hero-stamp">100%<br />is only<br />the start</span>
        </div>
      </section>

      <article className="cotton-article" id="story">
        <section className="cotton-opening" aria-label="Introduction">
          <div className="cotton-opening-label">
            <span>The question</span>
            <span>August 2026</span>
          </div>
          <div className="cotton-opening-copy">
            <p className="cotton-lead">
              <span>The easiest summer outfit on paper</span> is a cotton shirt
              with cotton trousers.
            </p>
            <p>
              Then the shirt feels fine all afternoon, the trousers do not, and
              the matching fiber label stops being very helpful.
            </p>
            <p>
              When I wrote about why I only wear linen in the summer, I kept
              coming back to fit and softness. Cotton deserves the same
              inspection.
            </p>
          </div>
          <div className="cotton-opening-copy">
            <p>
              Cotton is the fiber. Jersey, piqué, poplin, Oxford cloth,
              seersucker, twill, and denim are different ways that fiber can
              become fabric.
            </p>
            <p>
              Weight, lining, and cut finish the garment. That is why a
              100-percent-cotton label can be completely accurate and still
              leave out the part I need to know.
            </p>
            <p>
              The label tells me where to start. The actual garment has to
              finish the answer.
            </p>
            <a
              className="cotton-text-link"
              href="https://www.downsstyle.com/look-book/2024/7/1/why-i-only-wear-linen-in-the-summer"
              target="_blank"
              rel="noreferrer"
            >
              Read the linen story that started this series
            </a>
          </div>
        </section>

        <section className="cotton-label-decoder" aria-labelledby="decoder-title">
          <div className="cotton-section-heading">
            <p className="cotton-kicker">The label decoder</p>
            <h2 id="decoder-title">Same fiber. Four different jobs.</h2>
          </div>
          <div className="cotton-label-grid">
            {labelCards.map((card, index) => (
              <article key={card.name}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <p>{card.role}</p>
                <h3>{card.name}</h3>
                <small>{card.note}</small>
              </article>
            ))}
          </div>
        </section>

        <section className="cotton-story-section" id="tops" aria-labelledby="tops-title">
          <div className="cotton-story-copy">
            <p className="cotton-kicker">Above the waist</p>
            <h2 id="tops-title">The top half gets to be easy.</h2>
            <p>
              Jersey is the obvious place to begin because it gives us the
              T-shirt. The knitted fabric moves more naturally than a basic
              woven shirt, which is why a good cotton tee can feel so simple.
            </p>
            <p>
              The word jersey does not tell me the weight. One version can feel
              barely there; another can sit much closer to a sweatshirt. For
              hot weather, I would choose the lighter jersey with room through
              the body.
            </p>
            <p>
              Then piqué adds texture and a little more structure. I love that
              a polo can look more finished than a T-shirt without becoming a
              button-down. I would still touch the fabric before trusting the
              tiny texture in a photograph, because piqué can also be made
              heavy.
            </p>
            <details className="cotton-myth">
              <summary>Common error · Every cotton knit feels alike</summary>
              <p>
                Jersey and piqué are different knit constructions, and both
                come in different weights. The fiber percentage—or even the
                knit name—cannot tell you how light the finished shirt will
                feel.
              </p>
            </details>
            <p>
              Woven cotton changes the mood again. Poplin and chambray can give
              a shirt a crisp, clean surface, but the fabric does not move like
              jersey. This is where the cut has to help: an easy shoulder, room
              through the body, and no unnecessary lining.
            </p>
            <p>
              Oxford cloth is the one I would inspect most carefully. A fine
              version can work beautifully; a thick version can belong to
              another season. Gauze and voile move in the lighter direction,
              but a sheer shirt that needs another layer may give back the
              lightness that attracted me in the first place.
            </p>
            <p className="cotton-verdict">
              Overall, my favorite cotton top is not one fabric name. It is the
              one whose weight, cut, and layers agree.
            </p>
          </div>
          <figure className="cotton-story-image cotton-story-image-tall">
            <img
              src="/cotton/cotton-top.webp"
              alt="Man wearing a loose short-sleeve cream shirt with dark trousers outside"
              width="1200"
              height="2134"
              loading="lazy"
              decoding="async"
            />
            <figcaption>
              <strong>Recreate this:</strong> one relaxed woven shirt, one easy
              trouser, hard summer light, and enough frame to see the complete
              silhouette.
              <a
                href="https://www.pexels.com/photo/man-in-a-loose-shirt-and-creased-trousers-17500728/"
                target="_blank"
                rel="noreferrer"
              >
                Stock reference by ömer aliko / Pexels
              </a>
            </figcaption>
          </figure>
        </section>

        <section className="cotton-story-section cotton-story-reverse" id="bottoms" aria-labelledby="bottoms-title">
          <div className="cotton-story-copy">
            <p className="cotton-kicker">Below the waist</p>
            <h2 id="bottoms-title">The bottom has a harder job.</h2>
            <p>
              Trousers and shorts have to manage pockets, seams, movement, and
              enough structure to hold their shape. That is why the lightest
              cotton does not automatically make the best bottom.
            </p>
            <p>
              Twill is part of what makes chinos look clean. It is also why one
              pair can feel easy and another can feel dense. For summer, I
              would choose the lighter cloth with room through the leg.
            </p>
            <p>
              Seersucker brings more personality. The puckered surface makes
              the crinkle look intentional, but I would still check the fiber
              label and the inside. Seersucker names a construction, not a
              guaranteed weight, cotton content, or lack of lining.
            </p>
            <p>
              Denim makes the point obvious. A loose, lightweight denim short
              and rigid jeans can both be cotton. They are not the same summer
              decision.
            </p>
            <details className="cotton-myth">
              <summary>Common error · Denim is one fixed weight</summary>
              <p>
                Denim spans light shirting and substantial bottom weights. The
                name identifies the fabric family, not one temperature or one
                use. Pick up the actual garment before giving denim a season.
              </p>
            </details>
            <p>
              Jersey shorts reverse the problem. They can feel easy, but they
              look casual because they are casual. Sometimes softness is the
              whole assignment. Sometimes I want the bottom half of the outfit
              to hold a cleaner line.
            </p>
            <p className="cotton-verdict">
              Overall, the top can prioritize movement. The bottom needs enough
              structure without carrying more than the day requires.
            </p>
          </div>
          <figure className="cotton-story-image cotton-story-image-wide">
            <img
              src="/cotton/cotton-bottom.webp"
              alt="Man in a light shirt and tailored shorts walking through a sunny garden"
              width="1200"
              height="802"
              loading="lazy"
              decoding="async"
            />
            <figcaption>
              <strong>Recreate this:</strong> a full-body summer look in motion.
              Keep the background quiet and make the shorts or trousers easy to
              identify.
              <a
                href="https://www.pexels.com/photo/man-in-summer-outfit-7747271/"
                target="_blank"
                rel="noreferrer"
              >
                Stock reference by Enes Çelik / Pexels
              </a>
            </figcaption>
          </figure>
        </section>

        <section className="cotton-test" id="label-test" aria-labelledby="test-title">
          <div className="cotton-test-heading">
            <p className="cotton-kicker">Before I buy</p>
            <h2 id="test-title">The five-part label test.</h2>
            <p>
              I want the article to leave the reader with something useful in a
              fitting room, not another list of fabric names to memorize.
            </p>
          </div>
          <ol>
            {shoppingTest.map(([title, copy], index) => (
              <li key={title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{copy}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="cotton-test-note">
            <strong>One more distinction</strong>
            <p>
              Cotton can absorb moisture. That does not mean ordinary cotton
              dries quickly. If fast drying is the main job, I would look for a
              garment specifically designed and tested for that job.
            </p>
          </div>
        </section>

        <section className="cotton-closing" aria-labelledby="closing-title">
          <div>
            <p className="cotton-kicker">My answer</p>
            <h2 id="closing-title">Cotton is good for summer when the garment is.</h2>
          </div>
          <div className="cotton-closing-copy">
            <p>
              For an everyday summer outfit, my answer is simple: a lighter
              jersey or relaxed woven shirt on top; a light twill, unlined
              seersucker, or genuinely light denim below.
            </p>
            <p>
              Not because one construction is perfect, but because each part
              of the outfit is doing a different job.
            </p>
            <p>
              So, is cotton actually good for summer? Yes—when the fabric and
              the garment make sense. The fiber label alone has not earned the
              final word.
            </p>
            <p className="cotton-question">
              Before the next hot day, look at the cotton pieces you already
              own. Which one do you reach for, and which one do you regret by
              noon? I want to know what the labels say on both.
            </p>
          </div>
        </section>

        <section className="cotton-faq" aria-labelledby="faq-title">
          <div className="cotton-section-heading">
            <p className="cotton-kicker">The quick answers</p>
            <h2 id="faq-title">Cotton in summer, without the sales pitch.</h2>
          </div>
          <div className="cotton-faq-list">
            {faqs.map((faq) => (
              <details key={faq.question}>
                <summary>{faq.question}</summary>
                <p>{faq.answer}</p>
              </details>
            ))}
          </div>
        </section>
      </article>

      <section className="cotton-handoff" data-nosnippet aria-labelledby="handoff-title">
        <figure>
          <img
            src="/cotton/label-check.webp"
            alt="Red and white striped shirt on a wooden hanger with a blank tag"
            width="1000"
            height="1500"
            loading="lazy"
            decoding="async"
          />
          <figcaption>
            Label-check composition reference by Atlantic Ambience / Pexels.
            Recreate with a verified cotton garment and its real care label.
          </figcaption>
        </figure>
        <div>
          <p className="cotton-kicker">Private launch package · not article copy</p>
          <h2 id="handoff-title">One story, four useful entry points.</h2>
          <dl>
            <div>
              <dt>Search title</dt>
              <dd>Is Cotton Good for Summer? What the Label Leaves Out</dd>
            </div>
            <div>
              <dt>Social hook</dt>
              <dd>
                Two shirts can both say 100% cotton and feel completely
                different by noon. Here is what the label leaves out.
              </dd>
            </div>
            <div>
              <dt>Comment prompt</dt>
              <dd>Which cotton piece do you regret wearing when it gets hot?</dd>
            </div>
            <div>
              <dt>Current hashtag set</dt>
              <dd>#SummerStyle #SummerOutfits #MensFashionTips #HowToStyle #Cotton</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="cotton-research" data-nosnippet aria-labelledby="research-title">
        <div>
          <p className="cotton-kicker">Research desk</p>
          <h2 id="research-title">The technical notes stay behind the story.</h2>
        </div>
        <ul>
          {sources.map(([label, href]) => (
            <li key={href}>
              <a href={href} target="_blank" rel="noreferrer">
                {label}
              </a>
            </li>
          ))}
        </ul>
        <p>
          CottonWorks, Supima, and Cotton Incorporated are industry sources.
          They are used for narrow terminology and construction details—not
          universal quality, health, or sustainability claims.
        </p>
      </section>

      <footer className="cotton-footer">
        <div>
          <span className="footer-mark">DS</span>
          <p>
            Cotton article review for Charles.
            <br />
            Stock images are shot references, not final publication art.
          </p>
        </div>
        <a href="#top">Back to the top</a>
      </footer>
    </main>
  );
}
