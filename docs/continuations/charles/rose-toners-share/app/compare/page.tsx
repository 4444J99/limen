import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader } from "../site-header";

export const metadata: Metadata = {
  title: "Compare the rosewater drafts | Downs Style Studio",
  description:
    "Read the original, human, and edited rosewater drafts side by side, with every editorial decision in view.",
  openGraph: {
    title: "One ingredient. Three versions.",
    description:
      "A complete three-panel editorial comparison for the Downs Style rosewater story.",
    images: [
      {
        url: "/og-comparison.png",
        width: 1536,
        height: 804,
        alt: "Three versions of the Downs Style rosewater article",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    images: ["/og-comparison.png"],
  },
};

type ComparisonSection = {
  id: string;
  number: string;
  title: string;
  original: string;
  human: string;
  edited: string;
  decision: string;
};

function thoughtClusters(...clusters: string[]) {
  return clusters.join("\n\n");
}

const sections: ComparisonSection[] = [
  {
    id: "title",
    number: "00",
    title: "Article title",
    original:
      "Rose Toners and the Benefits Behind Our Favorite Scent",
    human:
      "Rose Toners and the Benefits Behind Our Favorite Scent",
    edited:
      "Rosewater and the Benefits Behind Our Favorite Flower",
    decision:
      "Applied the newer spoken title: rosewater is now the searchable subject, while favorite flower keeps the warmth Charles approved. Benefits remain carefully qualified in the article.",
  },
  {
    id: "opening",
    number: "01",
    title: "Seasonal opening",
    original:
      "With summer upon us here, the sweltering heat has left our skin with the need for some consistent refreshment, perhaps you noticed the heat making your usual skin care routine a bit futile in the face of this extreme weather we’re facing. If this is the case then here we offer an oasis of skincare that we think will help you cope with this unruly weather.",
    human:
      "With summer upon us here, the sweltering heat has left our skin with the need for some consistent refreshment, perhaps you noticed the heat making your usual skin care routine a bit futile in the face of this extreme weather we’re facing. If this is the case then here we offer an oasis of skincare that we think will help you cope with this unruly weather.",
    edited: thoughtClusters(
      "With summer upon us, the sweltering heat has left our skin in need of some consistent refreshment.",
      "Perhaps you have noticed the heat making your usual skincare routine feel a bit futile in the face of this extreme weather.",
      "If this is the case, then here we offer an oasis of skincare that we think will help you cope with this unruly weather.",
      "Rose has always been one of our favorite skincare ingredients, partly because it smells wonderful and partly because it makes an ordinary face mist feel a little more special.",
      "The scent gets our attention, but the formula is what makes us stay.",
      "Mario Badescu keeps the flower light and familiar, whereas Whamisa turns it into a toner so rich it is almost pretending to be a serum.",
      "Then Chantecaille takes the drama away again and leaves us with two ingredients, only for Fresh to bring the whole toner ritual roaring back. Same favorite flower, completely different personalities.",
    ),
    decision:
      "Kept Charles's season, we/our perspective, affection for rose, and slightly dramatic reactions. The new sentences still answer one another, but they now sound like his original introduction instead of an editor's summary.",
  },
  {
    id: "rosewater-note",
    number: "02",
    title: "Why rosewater belongs here",
    original: "",
    human: "",
    edited: thoughtClusters(
      "So why does rosewater keep finding its way back into our routines?",
      "It is the fragrant water collected when rose petals are distilled, which helps explain why it is more interesting than perfumed tap water.",
      "Laboratory studies have measured antioxidant activity in rose distillation products, which sounds extremely glamorous.",
      "Still, that result belongs to the material studied and not automatically to every pink bottle on a shelf.",
      "The type of rose matters, but so do the way it was distilled and the amount inside; after that, every other ingredient gets a chance to help the flower or completely crowd it out.",
      "Rose starts the story, but the whole bottle gets the final word.",
    ),
    decision:
      "Kept the evidence and its limitation, but translated the textbook language into Charles's habit of getting excited and then checking himself with an honest aside.",
  },
  {
    id: "mario",
    number: "03",
    title: "Mario Badescu",
    original:
      "Mario Badescu’s Facial Spray With Aloe, Herbs And Rosewater\n\nIf you had any sort of affliction with skincare like we did in the late 2010’s then you already know about Mario Badescu’s iconic skincare products. From your favorite celebrities to your next door neighbors someone you knew owned at least one of their products (if not this toner specifically) . Not without good cause of course, their au natural formulation was the much needed counter balance to the heavy makeup looks frequently worn in that era. We love this product for its rejuvenating effect on the skin which is due to its Bladderwrack (Seaweed) Extract, this ingredient is known for nourishing and hydrating skin, it’s said to improve evenness in overall skin tone and help with skin texture. With the sweet subtle aroma of the Damascan rose flower water this product features alongside aloe vera which contains anti inflammatory properties its easy to see why this is one of our summertime essentials.",
    human:
      "Mario Badescu’s Facial Spray With Aloe, Herbs And Rosewater\n\nIf you had any sort of affliction with skincare like we did in the late 2010’s then you already know about Mario Badescu’s iconic skincare products. From your favorite celebrities to your next door neighbors someone you knew owned at least one of their products (if not this toner specifically) . Not without good cause of course, their au natural formulation was the much needed counter balance to the heavy makeup looks frequently worn in that era. We love this product for its rejuvenating effect on the skin which is due to its Bladderwrack (Seaweed) Extract, this ingredient is known for nourishing and hydrating skin, it’s said to improve evenness in overall skin tone and help with skin texture. With the sweet subtle aroma of the Damascan rose flower water this product features alongside aloe vera which contains anti inflammatory properties its easy to see why this is one of our summertime essentials.",
    edited: thoughtClusters(
      "Mario Badescu Facial Spray With Aloe, Herbs And Rosewater",
      "If you had any sort of affliction with skincare like we did in the late 2010s, then you already know this bottle. From your favorite celebrities to your next-door neighbor, someone you knew owned at least one Mario Badescu product, if not this one specifically.",
      "Not without good cause, of course. Rosewater and aloe give the facial spray the light, refreshing personality we all remember, while the supporting botanicals kept it from feeling like plain floral water.",
      "The nostalgia is real, although it cannot answer what is in the bottle now. The current label lists Red 40 and Yellow 5, which does not need to become a medical panic to be worth mentioning.",
      "If you want a dye-free mist, this romance ends here; if you do not, the bottle is still very easy to understand. We just cannot call the formula all-natural anymore.",
    ),
    decision:
      "Restored the original affliction, celebrity-to-neighbor scale, and Not without good cause aside. Unsupported treatment claims still came out, while the current dye disclosure stays factual and calm.",
  },
  {
    id: "whamisa",
    number: "04",
    title: "Whamisa",
    original:
      "Whamsica organic’s Organic Flowers Toner Deep Rich\n\nThis South Korean brand has been on our radar this last year for many reasons...",
    human:
      "Whamsica organic’s Organic Flowers Toner Deep Rich\n\nThis South Korean brand has been on our radar for its botanical formulas and thoughtful packaging. Instead of beginning with water, this toner uses an aloe vera extract base, then adds glycerin and a fermented complex of rosebud, calendula, dandelion, hibiscus, jasmine, lavender, chamomile, and lotus. The texture is rich, bouncy, and closer to a thin serum than the watery toners many of us grew up using. The drawback is also part of its personality: rosewood, bergamot, bitter orange, Damask rose, and geranium oils give it a full essential-oil bouquet. Choose this when you want cushion and scent, not a barely-there, fragrance-minimal step.",
    edited: thoughtClusters(
      "Whamisa Organic Flowers Toner Deep Rich",
      "Whamisa does not even try to be Mario. This toner begins with an aloe base, which gives it a rich, bouncy texture much closer to a thin serum than the watery toners many of us grew up using.",
      "The fermented flower complex makes the formula even more interesting, but the real surprise is that all of that richness does not stay quiet.",
      "Several essential oils make the Damask rose smell full and obvious, which is fun when you want skincare to feel like an actual event.",
      "That same bouquet may be too much if you want a fragrance-minimal step; then again, a whisper was clearly never the point.",
    ),
    decision:
      "Treated the phone-call comment as criticism: removed the brand-site language and ingredient inventory, kept the texture Charles liked, and restored his excited reaction before admitting the scent drawback.",
  },
  {
    id: "santa-maria-novella",
    number: "05",
    title: "Santa Maria Novella",
    original: "",
    human: "",
    edited: thoughtClusters(
      "Santa Maria Novella Acqua di Rose",
      "Whamisa makes rose feel modern and fermented, whereas Santa Maria Novella makes it feel as though we should be applying it in a Florentine apothecary.",
      "The brand says Acqua di Rose has been documented at its Officina since 1381, which is so old it almost makes the rest of our routines look impatient.",
      "Distilled Damask rose water keeps the flower at the center of that history. History is romantic, but it does not make the formula minimal.",
      "Added fragrance and fragrant rose components turn this into the full apothecary experience, so we would choose it for the ritual rather than pretend it is a modern, active-driven treatment.",
    ),
    decision:
      "Added the missing heritage option in Charles's delighted, personal register, while still attributing the history to the brand and disclosing fragrance instead of repeating old medicinal claims.",
  },
  {
    id: "chantecaille",
    number: "06",
    title: "Chantecaille",
    original: "",
    human:
      "Chantecaille Pure Rosewater\n\nChantecaille offers a great choice out of the group with a two-ingredient list: Rose de Mai flower water and lactobacillus ferment. The brand steam-distills the whole Rose de Mai blossom in artesian well water in the South of France, giving this mist its naturally rosy aroma. We like the clarity of knowing exactly what is in the bottle. Still, this is a light mist, not a substantial lotion, so it may feel almost too simple if you want a toner with a richer texture or a broader botanical blend.",
    edited: thoughtClusters(
      "Chantecaille Pure Rosewater",
      "After nearly seven centuries of history, Chantecaille makes two ingredients feel almost rebellious.",
      "Pure Rosewater pairs Rose de Mai flower water with lactobacillus ferment, and that is actually the entire formula.",
      "The brand steam-distills the whole blossom in artesian well water in the South of France, so the aroma comes from the rose rather than an added fragrance blend.",
      "We love knowing exactly what is in the bottle, although that clarity can feel almost suspiciously simple when you expect a toner to bring more texture.",
      "If a simple formula makes you super excited, this is probably the one; if you want something more substantial, two ingredients may feel almost too simple.",
    ),
    decision:
      "Kept the two-ingredient fact, but framed it through Charles's genuine excitement and a playful qualification rather than a bare inventory.",
  },
  {
    id: "sisley",
    number: "07",
    title: "Sisley-Paris",
    original: "",
    human:
      "Sisley-Paris Floral Toning Lotion\n\nSisley-Paris lands on the traditional side with a classic wipe-on lotion made with rose, cornflower, and witch-hazel floral waters. It is the option for anyone who likes the familiar feeling of finishing a cleanse with a cotton pad before moving on to serum and moisturizer.",
    edited: thoughtClusters(
      "Sisley-Paris Floral Toning Lotion",
      "If Chantecaille makes two ingredients feel exciting, Sisley-Paris has no interest in stopping there.",
      "Rose opens the formula, but cornflower and witch-hazel floral waters turn it into the kind of classic wipe-on lotion that finishes a cleanse before serum and moisturizer.",
      "That fuller formula is less minimal, although that is not automatically an insult. Some routines want a light mist, while others want the familiar satisfaction of a cotton pad.",
      "Fragrance comes along with that traditional experience because Sisley was clearly not trying to be shy either.",
    ),
    decision:
      "Retained the traditional toner framing and added the missing fragrance disclosure and comparison point.",
  },
  {
    id: "fresh",
    number: "08",
    title: "Fresh",
    original: "Not present in Charles's original draft.",
    human: "Not present in Charles's original draft.",
    edited: thoughtClusters(
      "Fresh Rose Deep Hydration Facial Toner",
      "If Sisley-Paris is the toner for someone who misses a cotton pad, Fresh is what happens when that same ritual wants to look a little more romantic.",
      "The current formula combines Damask rose water and extracts with glycerin and hyaluronic acid, so the hydration story is more built out than the floral waters before it.",
      "That fullness is also the drawback: rose flower oil and fragrant rose components make this a very committed rose bottle, not a minimal one pretending to be invisible.",
      "Choose it when you want the flower and the toner step to feel equally obvious; click the photo to inspect the full formula or shop the bottle.",
    ),
    decision:
      "Added the supplied sixth product after Sisley-Paris and kept the reaction connected: the cotton-pad ritual returns with more hydration, more romance, and a clearer fragrance drawback.",
  },
  {
    id: "affiliate-disclosure",
    number: "09",
    title: "Affiliate disclosure",
    original: "Not present in Charles's original draft.",
    human: "Not present in Charles's original draft.",
    edited: thoughtClusters(
      "Affiliate disclosure: This post contains an affiliate link. If you buy through it, Downs Style may earn a commission at no extra cost to you. As an Amazon Associate I earn from qualifying purchases.",
      "Paid link — Downs Style may earn a commission if you shop this product",
    ),
    decision:
      "Placed the general disclosure before every shopping link and the paid-link notice directly beside Fresh, where the reader makes the shopping decision.",
  },
  {
    id: "closing",
    number: "10",
    title: "Closing comparison",
    original: "",
    human:
      "So, which rose is for you? Mario Badescu is the nostalgic mist, with a clear dye caveat. Whamisa is the rich, fermented, essential-oil bouquet. Santa Maria Novella brings Damask rose and centuries of apothecary history. Chantecaille keeps things to two ingredients, while Sisley-Paris gives us the most traditional floral-toner experience. We will keep testing the bottles that make skincare feel less like a chore and more like a small daily ritual, so come back for more honest skincare reviews soon.",
    edited: thoughtClusters(
      "By now, the right rose is probably obvious: the bottle whose drawback annoys you the least and whose personality sounds the most like your own.",
      "If the late-2010s nostalgia still has you, the Mario Badescu photo is worth one more click so you can look at the current formula yourself before deciding whether the dyes end the romance.",
      "Whamisa answers that light little mist with a toner that almost behaves like a serum, which makes its photo the one to click when you want to see whether the aloe base and fermented flowers are rich enough to earn an extra step.",
      "That modern richness makes Santa Maria Novella feel even more old-world by comparison; click its photo for the Damask-rose apothecary ritual, because sometimes the ritual is honestly the entire point.",
      "Chantecaille takes the drama away again and gives minimalists a very good reason to click its photo: two ingredients, Rose de Mai, and nowhere for the formula to hide.",
      "Sisley-Paris brings us back to the traditional toner, so its photo is the one to open if rose, cornflower, witch hazel, and a cotton pad sound more satisfying than another mist.",
      "Fresh makes that traditional step feel a little more romantic again, so its photo is the one to click if glycerin, hyaluronic acid, and a very committed rose formula sound like your kind of finale.",
      "To shop, click any product photo above. Each of the six goes straight to the same product page we used while reviewing it, so you can compare the formulas for yourself before choosing—and then come back, because we will keep testing the bottles that make skincare feel less like a chore and more like a small daily ritual.",
    ),
    decision:
      "Removed the product-by-product recap and replaced it with one continuous sequence in which each bottle answers the last, then carried Fresh through the final invitation as the sixth and final reaction.",
  },
];

type DiffPart = {
  type: "same" | "added" | "removed";
  value: string;
};

function tokenize(text: string) {
  return text.match(/\s+|[\p{L}\p{N}’'-]+|[^\s]/gu) ?? [];
}

function diffWords(before: string, after: string): DiffPart[] {
  const left = tokenize(before);
  const right = tokenize(after);
  const rows = left.length + 1;
  const columns = right.length + 1;
  const matrix = Array.from({ length: rows }, () =>
    Array<number>(columns).fill(0),
  );

  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      matrix[i][j] =
        left[i] === right[j]
          ? matrix[i + 1][j + 1] + 1
          : Math.max(matrix[i + 1][j], matrix[i][j + 1]);
    }
  }

  const parts: DiffPart[] = [];
  const push = (type: DiffPart["type"], value: string) => {
    const previous = parts.at(-1);
    if (previous?.type === type) previous.value += value;
    else parts.push({ type, value });
  };

  let i = 0;
  let j = 0;
  while (i < left.length && j < right.length) {
    if (left[i] === right[j]) {
      push("same", left[i]);
      i += 1;
      j += 1;
    } else if (matrix[i + 1][j] >= matrix[i][j + 1]) {
      push("removed", left[i]);
      i += 1;
    } else {
      push("added", right[j]);
      j += 1;
    }
  }
  while (i < left.length) push("removed", left[i++]);
  while (j < right.length) push("added", right[j++]);
  return parts;
}

function DraftText({ text }: { text: string }) {
  if (!text) {
    return (
      <p className="empty-copy">
        <span>Not written yet</span>
        This section was absent from this version.
      </p>
    );
  }

  return <p className="version-copy">{text}</p>;
}

function EditedDiff({ before, after }: { before: string; after: string }) {
  const parts = diffWords(before, after);
  return (
    <p className="version-copy diff-copy">
      {parts.map((part, index) => {
        if (part.type === "added") {
          return <ins key={`${part.type}-${index}`}>{part.value}</ins>;
        }
        if (part.type === "removed") {
          return <del key={`${part.type}-${index}`}>{part.value}</del>;
        }
        return <span key={`${part.type}-${index}`}>{part.value}</span>;
      })}
    </p>
  );
}

export default function CompareDrafts() {
  return (
    <main className="compare-page" id="top">
      <SiteHeader active="compare" />

      <section className="compare-hero">
        <p className="kicker">Rose as an ingredient · Three-panel comparison</p>
        <h1>
          One ingredient. Three versions.
          <em>Every change in view.</em>
        </h1>
        <div className="compare-intro">
          <p>
            Read each section left to right: the unfinished snapshot we first
            received, the human copy currently live on Downs Style, and the
            proposed ingredient-led edit with every insertion and deletion
            marked—including the new title. The added white space is also an
            edit: each paragraph now holds one long sentence or one short,
            connected thought cluster.
          </p>
          <a className="primary-link" href="#comparison-board">
            See the changes <span aria-hidden="true">↓</span>
          </a>
        </div>
      </section>

      <section className="comparison-board" id="comparison-board">
        <div className="panel-headings" aria-hidden="true">
          <div>
            <span>01</span>
            <strong>Original draft</strong>
            <small>First unfinished snapshot</small>
          </div>
          <div>
            <span>02</span>
            <strong>Human draft</strong>
            <small>Current live Downs Style copy</small>
          </div>
          <div>
            <span>03</span>
            <strong>All edits</strong>
            <small>
              <i className="legend-added">Added</i>
              <i className="legend-removed">Removed</i>
            </small>
          </div>
        </div>

        {sections.map((section) => (
          <article className="comparison-row" id={section.id} key={section.id}>
            <header className="row-heading">
              <span>{section.number}</span>
              <h2>{section.title}</h2>
            </header>

            <div className="version-panel original-panel">
              <p className="mobile-panel-label">Original draft</p>
              <DraftText text={section.original} />
            </div>

            <div className="version-panel human-panel">
              <p className="mobile-panel-label">Human draft</p>
              <DraftText text={section.human} />
            </div>

            <div className="version-panel edited-panel">
              <p className="mobile-panel-label">All edits</p>
              <EditedDiff before={section.human} after={section.edited} />
              <aside className="editor-decision">
                <span>Why it changed</span>
                <p>{section.decision}</p>
              </aside>
            </div>
          </article>
        ))}
      </section>

      <section className="comparison-cta">
        <p className="kicker">Ready to review</p>
        <h2>The full edited story is on page one.</h2>
        <p>
          The comparison stays attached so Charles can approve the voice,
          verify the ingredient-first language, and see exactly what was
          retained.
        </p>
        <Link className="primary-link" href="/">
          Read the finished article <span aria-hidden="true">↗</span>
        </Link>
      </section>

      <footer>
        <div>
          <span className="footer-mark">DS</span>
          <p>
            Original, human, and edited copy.
            <br />
            Not yet published on Downs Style.
          </p>
        </div>
        <a
          href="https://www.downsstyle.com/skincare/2026/8/1/rose-toners-and-the-benefits-behind-our-favorite-scent"
          target="_blank"
          rel="noreferrer"
        >
          Open the live draft <span aria-hidden="true">↗</span>
        </a>
      </footer>
    </main>
  );
}
