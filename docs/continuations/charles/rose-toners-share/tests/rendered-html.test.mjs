import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const templateRoot = new URL("../", import.meta.url);

const unchangedShoppingUrls = [
  "https://www.mariobadescu.com/products/facial-spray-with-aloe-herbs-and-rosewater",
  "https://whamisa.us/products/organic-flowers-toner-deep-rich",
  "https://us.smnovella.com/products/adr",
  "https://chantecaille.com/products/pure-rosewater",
  "https://www.saksfifthavenue.com/product/sisley-paris-floral-toning-lotion-0446264201031.html",
];

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("image optimization fails clearly when its binding is absent", async () => {
  const response = await render("/_vinext/image?url=%2Fog.png&w=640&q=75");
  assert.equal(response.status, 501);
  assert.equal(await response.text(), "Image optimization is not configured");
});

test("server-renders the complete six-product editorial preview", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(
    html,
    /<title>Rosewater and the Benefits Behind Our Favorite Flower \| Downs Style<\/title>/i,
  );
  assert.match(html, /og-comparison\.png/);
  assert.match(html, /six toners and face mists/i);
  assert.match(html, /Rose in Skincare/);
  assert.match(html, /Our Favorite Flower/);
  assert.match(html, /oasis of skincare/);
  assert.match(html, /unruly weather/);
  assert.equal((html.match(/class="opening-cluster"/g) ?? []).length, 2);
  assert.match(html, /<\/p><p>Not without good cause/);
  assert.match(html, /<\/p><p>The fermented flower complex/);
  assert.match(html, /Rose has always been one of our favorite skincare ingredients/);
  assert.match(html, /So why does rosewater keep finding its way back/);
  assert.match(html, /result belongs to the material studied/);
  assert.match(html, /aria-label="Shop Mario Badescu Facial Spray/);
  assert.match(html, /Mario Badescu Facial Spray/);
  assert.match(html, /Whamisa Organic Flowers Toner Deep Rich/);
  assert.match(html, /Whamisa does not even try to be Mario/);
  assert.match(html, /this romance ends here/);
  assert.match(html, /which sounds extremely glamorous/);
  assert.match(html, /a whisper was clearly never the point/);
  assert.match(html, /Santa Maria Novella Acqua di Rose/);
  assert.match(html, /Chantecaille Pure Rosewater/);
  assert.match(html, /Sisley-Paris Floral Toning Lotion/);
  assert.match(html, /Fresh Rose Deep Hydration Facial Toner/);
  assert.match(html, /bring the whole toner ritual roaring back/);
  assert.match(html, /glycerin and hyaluronic acid/);
  assert.match(html, /Affiliate disclosure/);
  assert.match(html, /As an Amazon Associate I earn from qualifying purchases/);
  assert.match(html, /Paid link — Downs Style may earn a commission/);
  assert.match(html, /Each of the six goes straight/);
  assert.equal((html.match(/<section class="product/g) ?? []).length, 6);
  const disclosurePosition = html.indexOf("Affiliate disclosure");
  assert.notEqual(disclosurePosition, -1);
  for (const url of unchangedShoppingUrls) {
    assert.equal(html.split(`href="${url}"`).length - 1, 2);
    assert.ok(html.indexOf(`href="${url}"`) > disclosurePosition);
  }
  assert.equal(
    (
      html.match(
        /href="https:\/\/on\.ltk\.com\/\+IRLNZ3842CX6uNfhjQ9edg"/g,
      ) ?? []
    ).length,
    2,
  );
  assert.match(html, /Red 40 and Yellow 5/);
  assert.match(html, /Charles(?:&apos;|&#x27;|')s photo goes here/);
  assert.match(html, /Which formula fits your routine\?/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/);
  assert.doesNotMatch(html, /thoughtful packaging|fermented complex of rosebud/);
  assert.doesNotMatch(html, /comparison-grid|formula-note/);
  assert.doesNotMatch(html, /\$\d/);
  assert.match(html, /href="\/archive"/);
  assert.match(html, /href="\/voice"/);
});

test("server-renders the three-panel draft comparison", async () => {
  const response = await render("/compare");
  assert.equal(response.status, 200);

  const html = await response.text();
  assert.match(html, /Original draft/);
  assert.match(html, /Human draft/);
  assert.match(html, /All edits/);
  assert.match(html, /First unfinished snapshot/);
  assert.match(html, /Current live Downs Style copy/);
  assert.match(html, /Why it changed/);
  assert.match(html, /added white space is also an edit/);
  assert.match(html, /Article title/);
  assert.match(html, /Rose Toners and the Benefits Behind Our Favorite Scent/);
  assert.match(html, /Applied the newer spoken title/);
  assert.match(html, /favorite flower keeps the warmth Charles approved/);
  assert.match(html, /slightly dramatic reactions/);
  assert.match(html, /Why rosewater belongs here/);
  assert.match(html, /getting excited and then checking himself/);
  assert.match(html, /Treated the phone-call comment as criticism/);
  assert.match(html, /removed the brand-site language/);
  assert.match(html, /Removed the product-by-product recap/);
  assert.match(html, /Whamsica/);
  assert.match(html, /Whamisa/);
  assert.match(html, /Organic Flowers Toner Deep Rich/);
  assert.match(html, /Santa Maria Novella Acqua di Rose/);
  assert.match(html, /current dye disclosure stays factual and calm/);
  assert.match(html, /<ins>/);
  assert.match(html, /<del>/);
  assert.equal((html.match(/class="comparison-row"/g) ?? []).length, 11);
  assert.match(html, /id="fresh"/);
  assert.match(html, /<h2>Fresh<\/h2>/);
  assert.match(html, /committed rose bottle/);
  assert.match(html, /Not present in Charles(?:&apos;|&#x27;|')s original draft/);
  assert.match(html, /Paid link — Downs Style may earn a commission/);
  assert.match(html, /Each of the six goes straight/);
  assert.match(html, /All 258 posts/);
  assert.match(html, /Voice system/);
});

test("server-renders the cotton article and private launch package", async () => {
  const response = await render("/cotton");
  assert.equal(response.status, 200);

  const html = await response.text();
  assert.match(
    html,
    /<title>Is Cotton Good for Summer\? What the Label Leaves Out \| Downs Style<\/title>/i,
  );
  assert.match(html, /name="robots" content="noindex, nofollow"/i);
  assert.match(html, /Is cotton actually/);
  assert.match(html, /good for summer\?/);
  assert.match(html, /Both can say 100% cotton/);
  assert.match(html, /The label tells me where to start/);
  assert.match(html, /Same fiber\. Four different jobs/);
  assert.match(html, /The top half gets to be easy/);
  assert.match(html, /The bottom has a harder job/);
  assert.match(html, /The five-part label test/);
  assert.match(html, /Cotton is good for summer when the garment is/);
  assert.match(html, /Cotton in summer, without the sales pitch/);
  assert.equal((html.match(/<details/g) ?? []).length, 6);
  assert.match(html, /Private launch package · not article copy/);
  assert.match(html, /#SummerStyle #SummerOutfits #MensFashionTips #HowToStyle #Cotton/);
  assert.match(html, /Stock reference by ömer aliko \/ Pexels/);
  assert.match(html, /Stock reference by Enes Çelik \/ Pexels/);
  assert.match(html, /application\/ld\+json/);
  assert.match(html, /BlogPosting/);
  assert.doesNotMatch(html, /full circle moment/i);
  assert.doesNotMatch(html, /autumn in denial/i);
  assert.doesNotMatch(html, /botanical backstory/i);
  assert.doesNotMatch(html, /stop behaving like armor/i);
});

test("server-renders all 258 archive records without article bodies or tags", async () => {
  const response = await render("/archive");
  assert.equal(response.status, 200);

  const html = await response.text();
  assert.match(html, /The whole history/);
  assert.match(html, /finally in one room/);
  assert.match(html, /258 pieces across nine editorial worlds/);
  assert.equal((html.match(/data-archive-entry/g) ?? []).length, 258);
  assert.match(html, /Rose Water and the benefits behind our favorite flower/);
  assert.match(html, /My Favorite Candles of the Year/);
  assert.match(html, /Skincare/);
  assert.match(html, /Masks/);
  assert.match(html, /Look Book/);
  assert.match(html, /Interior Design/);
  assert.match(html, /Search the archive/);
  assert.match(html, /Calendar span/);
  assert.match(html, /og-archive\.png/);
  assert.doesNotMatch(html, /candle junkie|luxury scents/);
});

test("server-renders the evidence-backed Charles voice system", async () => {
  const response = await render("/voice");
  assert.equal(response.status, 200);

  const html = await response.text();
  assert.match(html, /His voice was/);
  assert.match(html, /already there/);
  assert.match(html, /257-post causal baseline/);
  assert.match(html, /76,597/);
  assert.match(html, /alphabetic tokens in the historical baseline/);
  assert.match(html, /45\.01/);
  assert.match(html, /0\.98/);
  assert.match(html, /154×/);
  assert.match(html, /I is the fingerprint/);
  assert.match(html, /Thematic core/);
  assert.match(html, /Natural Center/);
  assert.match(html, /Channel profile/);
  assert.match(html, /How to properly let a candle burn/);
  assert.match(html, /Transcend Cosmetics becomes Transcend Essentials/);
  assert.match(html, /The summer fabric sequence/);
  assert.match(html, /compact myth check/);
  assert.match(html, /og-archive\.png/);
});

test("archive data is a bounded seven-field public ledger", async () => {
  const posts = JSON.parse(
    await readFile(new URL("../data/posts.json", import.meta.url), "utf8"),
  );
  const expectedKeys = [
    "publishedDate",
    "year",
    "category",
    "title",
    "url",
    "author",
    "wordCount",
  ];

  assert.equal(posts.length, 258);
  assert.equal(new Set(posts.map((post) => post.url)).size, 258);
  for (const post of posts) {
    assert.deepEqual(Object.keys(post), expectedKeys);
    assert.match(post.url, /^https:\/\/www\.downsstyle\.com\//);
    assert.equal("body" in post, false);
    assert.equal("tags" in post, false);
  }
});

test("removes starter-only preview assets and dependencies", async () => {
  const packageJson = await readFile(new URL("../package.json", import.meta.url), "utf8");
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);

  await assert.rejects(access(new URL("app/_sites-preview", templateRoot)));
});
