import type { Metadata } from "next";
import { SiteHeader } from "./site-header";

export const metadata: Metadata = {
  title: {
    absolute:
      "Rosewater and the Benefits Behind Our Favorite Flower | Downs Style",
  },
  description:
    "An ingredient-aware look at rosewater across six toners and face mists, with honest notes on formula, texture, fragrance, and what sets each one apart.",
  openGraph: {
    title: "Rosewater and the Benefits Behind Our Favorite Flower",
    description:
      "Six rose toners and face mists, compared through formula, texture, fragrance, and ritual.",
    type: "article",
    images: [
      {
        url: "/og-comparison.png",
        width: 1536,
        height: 804,
        alt: "Rosewater and the Benefits Behind Our Favorite Flower",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    images: ["/og-comparison.png"],
  },
};

const marioImage =
  "https://images.squarespace-cdn.com/content/v1/5a249e6ad74cff08266045cf/551c3ea4-1b1c-482e-9a1d-806cc31225ee/IMG_3034.jpeg?format=1500w";

const whamisaImage =
  "https://images.squarespace-cdn.com/content/v1/5a249e6ad74cff08266045cf/2f254341-77c6-44d3-b3d8-ef92582ece40/whamsica.webp?format=1500w";

const products = [
  {
    number: "01",
    slug: "mario-badescu",
    label: "The nostalgic mist",
    title: "Mario Badescu Facial Spray With Aloe, Herbs And Rosewater",
    link: "https://www.mariobadescu.com/products/facial-spray-with-aloe-herbs-and-rosewater",
    image: marioImage,
    imageAlt: "Mario Badescu rose facial spray photographed by Charles",
    copy: (
      <>
        <p>
          If you had any sort of affliction with skincare like we did in the
          late 2010s, then you already know this bottle. From your favorite
          celebrities to your next-door neighbor, someone you knew owned at
          least one Mario Badescu product, if not this one specifically.
        </p>
        <p>
          Not without good cause, of course. Rosewater and aloe give the facial
          spray the light, refreshing personality we all remember, while the
          supporting botanicals kept it from feeling like plain floral water.
        </p>
        <p>
          The nostalgia is real, although it cannot answer what is in the
          bottle now. The current label lists Red 40 and Yellow 5, which does
          not need to become a medical panic to be worth mentioning.
        </p>
        <p>
          If you want a dye-free mist, this romance ends here; if you do not,
          the bottle is still very easy to understand. We just cannot call
          the formula all-natural anymore.
        </p>
      </>
    ),
  },
  {
    number: "02",
    slug: "whamisa",
    label: "The rich fermented toner",
    title: "Whamisa Organic Flowers Toner Deep Rich",
    link: "https://whamisa.us/products/organic-flowers-toner-deep-rich",
    image: whamisaImage,
    imageAlt: "Whamisa Organic Flowers Toner Deep Rich photographed by Charles",
    copy: (
      <>
        <p>
          Whamisa does not even try to be Mario. This toner begins with an aloe
          base, which gives it a rich, bouncy texture much closer to a thin
          serum than the watery toners many of us grew up using.
        </p>
        <p>
          The fermented flower complex makes the formula even more interesting,
          but the real surprise is that all of that richness does not stay
          quiet.
        </p>
        <p>
          Several essential oils make the Damask rose smell full and obvious,
          which is fun when you want skincare to feel like an actual event.
        </p>
        <p>
          That same bouquet may be too much if you want a fragrance-minimal
          step; then again, a whisper was clearly never the point.
        </p>
      </>
    ),
  },
  {
    number: "03",
    slug: "santa-maria-novella",
    label: "The heritage rosewater",
    title: "Santa Maria Novella Acqua di Rose",
    link: "https://us.smnovella.com/products/adr",
    imageAlt: "Photo placeholder for Santa Maria Novella Acqua di Rose",
    copy: (
      <>
        <p>
          Whamisa makes rose feel modern and fermented, whereas Santa Maria
          Novella makes it feel as though we should be applying it in a
          Florentine apothecary.
        </p>
        <p>
          The brand says Acqua di Rose has been documented at its Officina
          since 1381, which is so old it almost makes the rest of our routines
          look impatient.
        </p>
        <p>
          Distilled Damask rose water keeps the flower at the center of that
          history. History is romantic, but it does not make the formula
          minimal.
        </p>
        <p>
          Added fragrance and fragrant rose components turn this into the full
          apothecary experience, so we would choose it for the ritual rather
          than pretend it is a modern, active-driven treatment.
        </p>
      </>
    ),
  },
  {
    number: "04",
    slug: "chantecaille",
    label: "The minimalist mist",
    title: "Chantecaille Pure Rosewater",
    link: "https://chantecaille.com/products/pure-rosewater",
    imageAlt: "Photo placeholder for Chantecaille Pure Rosewater",
    copy: (
      <>
        <p>
          After nearly seven centuries of history, Chantecaille makes two
          ingredients feel almost rebellious.
        </p>
        <p>
          Pure Rosewater pairs Rose de Mai flower water with lactobacillus
          ferment, and that is actually the entire formula.
        </p>
        <p>
          The brand steam-distills the whole blossom in artesian well water in
          the South of France, so the aroma comes from the rose rather than an
          added fragrance blend.
        </p>
        <p>
          We love knowing exactly what is in the bottle, although that clarity
          can feel almost suspiciously simple when you expect a toner to bring
          more texture.
        </p>
        <p>
          If a simple formula makes you super excited, this is probably the
          one; if you want something more substantial, two ingredients may
          feel almost too simple.
        </p>
      </>
    ),
  },
  {
    number: "05",
    slug: "sisley-paris",
    label: "The traditional floral lotion",
    title: "Sisley-Paris Floral Toning Lotion",
    link: "https://www.saksfifthavenue.com/product/sisley-paris-floral-toning-lotion-0446264201031.html",
    imageAlt: "Photo placeholder for Sisley-Paris Floral Toning Lotion",
    copy: (
      <>
        <p>
          If Chantecaille makes two ingredients feel exciting, Sisley-Paris
          has no interest in stopping there.
        </p>
        <p>
          Rose opens the formula, but cornflower and witch-hazel floral waters
          turn it into the kind of classic wipe-on lotion that finishes a
          cleanse before serum and moisturizer.
        </p>
        <p>
          That fuller formula is less minimal, although that is not
          automatically an insult. Some routines want a light mist, while
          others want the familiar satisfaction of a cotton pad.
        </p>
        <p>
          Fragrance comes along with that traditional experience because
          Sisley was clearly not trying to be shy either.
        </p>
      </>
    ),
  },
  {
    number: "06",
    slug: "fresh",
    label: "The romantic finale",
    title: "Fresh Rose Deep Hydration Facial Toner",
    link: "https://on.ltk.com/+IRLNZ3842CX6uNfhjQ9edg",
    affiliate: true,
    imageAlt:
      "Photo placeholder for Fresh Rose Deep Hydration Facial Toner",
    copy: (
      <>
        <p>
          If Sisley-Paris is the toner for someone who misses a cotton pad,
          Fresh is what happens when that same ritual wants to look a little
          more romantic.
        </p>
        <p>
          The current formula combines Damask rose water and extracts with
          glycerin and hyaluronic acid, so the hydration story is more built
          out than the floral waters before it.
        </p>
        <p>
          That fullness is also the drawback: rose flower oil and fragrant rose
          components make this a very committed rose bottle, not a minimal one
          pretending to be invisible.
        </p>
        <p>
          Choose it when you want the flower and the toner step to feel equally
          obvious; click the photo to inspect the full formula or shop the
          bottle.
        </p>
      </>
    ),
  },
] as const;

function Arrow() {
  return <span aria-hidden="true">↗</span>;
}

export default function Home() {
  return (
    <main id="top">
      <SiteHeader active="article" />

      <section className="hero" aria-labelledby="page-title">
        <div className="hero-copy">
          <p className="kicker">
            Downs Style · Rose in Skincare · Draft for Charles
          </p>
          <h1 id="page-title">
            Rosewater
            <em>and the Benefits Behind</em>
            Our Favorite Flower
          </h1>
          <p className="dek">
            Six formulas show how rosewater and rose-derived ingredients can
            take very different forms—from a late-2010s icon to a
            two-ingredient French mist and one very committed rose finale.
          </p>
          <div className="hero-actions">
            <a className="primary-link" href="#article">
              Read the draft <span aria-hidden="true">↓</span>
            </a>
            <a className="secondary-link" href="/compare">
              See every edit <span aria-hidden="true">↗</span>
            </a>
            <span>Approx. 6 minute read</span>
          </div>
        </div>

        <div className="hero-art" aria-label="Charles's existing rose toner photography">
          <figure className="hero-photo hero-photo-main">
            <a
              href={`#${products[0].slug}`}
              aria-label={`Jump to ${products[0].title}`}
            >
              <img src={marioImage} alt="Mario Badescu rose facial spray" />
            </a>
          </figure>
          <figure className="hero-photo hero-photo-secondary">
            <a
              href={`#${products[1].slug}`}
              aria-label={`Jump to ${products[1].title}`}
            >
              <img src={whamisaImage} alt="Whamisa Organic Flowers toner" />
            </a>
          </figure>
          <div className="hero-seal" aria-hidden="true">
            <span>6</span>
            rose
            <br />
            formulas
          </div>
        </div>
      </section>

      <section className="opening" id="article">
        <div className="opening-label">
          <span>Editor&apos;s note</span>
          <span>August 2026</span>
        </div>
        <div className="opening-cluster">
          <p>
            <span className="drop-cap">W</span>ith summer upon us, the sweltering
            heat has left our skin in need of some consistent refreshment.
          </p>
          <p>
            Perhaps you have noticed the heat making your usual skincare
            routine feel a bit futile in the face of this extreme weather.
          </p>
          <p>
            If this is the case, then here we offer an oasis of skincare that we
            think will help you cope with this unruly weather.
          </p>
        </div>
        <div className="opening-cluster">
          <p>
            Rose has always been one of our favorite skincare ingredients,
            partly because it smells wonderful and partly because it makes an
            ordinary face mist feel a little more special.
          </p>
          <p>
            The scent gets our attention, but the formula is what makes us stay.
          </p>
          <p>
            Mario Badescu keeps the flower light and familiar, whereas Whamisa
            turns it into a toner so rich it is almost pretending to be a serum.
          </p>
          <p>
            Then Chantecaille takes the drama away again and leaves us with two
            ingredients, only for Fresh to bring the whole toner ritual roaring
            back. Same favorite flower, completely different personalities.
          </p>
        </div>
        <div className="ingredient-note">
          <p>
            So why does rosewater keep finding its way back into our routines?
          </p>
          <p>
            It is the fragrant water collected when rose petals are distilled,
            which helps explain why it is more interesting than perfumed tap
            water.
          </p>
          <p>
            <a
              href="https://dergipark.org.tr/en/pub/ankutbd/article/786544"
              target="_blank"
              rel="noreferrer"
            >
              Laboratory studies
            </a>{" "}
            have measured antioxidant activity in rose distillation products,
            which sounds extremely glamorous.
          </p>
          <p>
            Still, that result belongs to the material studied and not
            automatically to every pink bottle on a shelf.
          </p>
          <p>
            The type of rose matters, but so do the way it was distilled and
            the amount inside; after that, every other ingredient gets a chance
            to help the flower or completely crowd it out.
          </p>
          <p>Rose starts the story, but the whole bottle gets the final word.</p>
        </div>
      </section>

      <aside className="affiliate-disclosure" aria-label="Affiliate disclosure">
        <strong>Affiliate disclosure</strong>
        <p>
          This post contains an affiliate link. If you buy through it, Downs
          Style may earn a commission at no extra cost to you. As an Amazon
          Associate I earn from qualifying purchases.
        </p>
      </aside>

      <div className="product-list">
        {products.map((product, index) => (
          <section
            className={`product ${index % 2 === 1 ? "product-reverse" : ""}`}
            id={product.slug}
            key={product.slug}
          >
            <div className="product-media">
              {"image" in product ? (
                <a
                  className="product-image-link"
                  href={product.link}
                  target="_blank"
                  rel={
                    "affiliate" in product && product.affiliate
                      ? "sponsored noreferrer"
                      : "noreferrer"
                  }
                  aria-label={`Shop ${product.title}`}
                >
                  <img src={product.image} alt={product.imageAlt} />
                </a>
              ) : (
                <a
                  className="product-placeholder-link"
                  href={product.link}
                  target="_blank"
                  rel={
                    "affiliate" in product && product.affiliate
                      ? "sponsored noreferrer"
                      : "noreferrer"
                  }
                  aria-label={`Shop ${product.title}`}
                >
                  <span className={`photo-placeholder placeholder-${index}`}>
                    <span className="placeholder-orbit" aria-hidden="true" />
                    <span>Charles&apos;s photo goes here</span>
                    <strong>{product.title}</strong>
                  </span>
                </a>
              )}
              <span className="product-number">{product.number}</span>
            </div>

            <div className="product-copy">
              <p className="product-label">{product.label}</p>
              <h2>
                <a
                  href={product.link}
                  target="_blank"
                  rel={
                    "affiliate" in product && product.affiliate
                      ? "sponsored noreferrer"
                      : "noreferrer"
                  }
                >
                  {product.title}
                </a>
              </h2>
              {"affiliate" in product && product.affiliate ? (
                <p className="paid-link-notice">
                  Paid link — Downs Style may earn a commission if you shop
                  this product
                </p>
              ) : null}
              <div className="product-prose">{product.copy}</div>
            </div>
          </section>
        ))}
      </div>

      <section className="comparison" id="comparison">
        <div className="comparison-heading">
          <p className="kicker">The decision</p>
          <h2>Which formula fits your routine?</h2>
          <p>
            Start with the tension you care about most. Simplicity can make
            rose clearer, but structure can make the ritual more satisfying.
          </p>
        </div>

        <div className="decision-story decision-story-connected">
          <p>
            By now, the right rose is probably obvious: the bottle whose
            drawback annoys you the least and whose personality sounds the most
            like your own.
          </p>
          <p>
            If the late-2010s nostalgia still has you, the Mario Badescu photo
            is worth one more click so you can look at the current formula
            yourself before deciding whether the dyes end the romance.
          </p>
          <p>
            Whamisa answers that light little mist with a toner that almost
            behaves like a serum, which makes its photo the one to click when
            you want to see whether the aloe base and fermented flowers are
            rich enough to earn an extra step.
          </p>
          <p>
            That modern richness makes Santa Maria Novella feel even more
            old-world by comparison; click its photo for the Damask-rose
            apothecary ritual, because sometimes the ritual is honestly the
            entire point.
          </p>
          <p>
            Chantecaille takes the drama away again and gives minimalists a very
            good reason to click its photo: two ingredients, Rose de Mai, and
            nowhere for the formula to hide.
          </p>
          <p>
            Sisley-Paris brings us back to the traditional toner, so its photo
            is the one to open if rose, cornflower, witch hazel, and a cotton
            pad sound more satisfying than another mist.
          </p>
          <p>
            Fresh makes that traditional step feel a little more romantic
            again, so its photo is the one to click if glycerin, hyaluronic
            acid, and a very committed rose formula sound like your kind of
            finale.
          </p>
        </div>

        <p className="closing-copy">
          To shop, click any product photo above. Each of the six goes straight
          to the same product page we used while reviewing it, so you can
          compare the formulas for yourself before choosing—and then come back,
          because we will keep testing the bottles that make skincare feel less
          like a chore and more like a small daily ritual.
        </p>
      </section>

      <footer>
        <div>
          <span className="footer-mark">DS</span>
          <p>
            Downs Style Studio · archive, voice, and editorial preview.
            <br />
            Not yet published on Downs Style.
          </p>
        </div>
        <a href="/archive">
          Explore all 258 posts <Arrow />
        </a>
      </footer>
    </main>
  );
}
