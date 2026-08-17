import type { Metadata } from "next";
import postsData from "../../data/posts.json";
import { SiteHeader } from "../site-header";
import { ArchiveExplorer, type ArchivePost } from "./archive-explorer";

export const metadata: Metadata = {
  title: "The complete archive | Downs Style Studio",
  description:
    "Search and filter all 258 public Downs Style posts by Charles Downs, spanning skincare, candles, clothing, travel, food, interiors, and wellness.",
  openGraph: {
    title: "The complete Downs Style archive",
    description:
      "258 posts, nine editorial categories, and the full public history from 2017 onward.",
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

const posts: ArchivePost[] = postsData.map((post) => ({
  publishedDate: post.publishedDate,
  year: post.year,
  category: post.category,
  title: post.title,
  url: post.url,
  author: post.author,
  wordCount: post.wordCount,
}));

const categoryCounts = Array.from(
  posts.reduce((counts, post) => {
    counts.set(post.category, (counts.get(post.category) ?? 0) + 1);
    return counts;
  }, new Map<string, number>()),
)
  .map(([label, count]) => ({ label, count }))
  .sort((left, right) => right.count - left.count);

const years = Array.from(new Set(posts.map((post) => post.year))).sort(
  (left, right) => Number(right) - Number(left),
);

export default function ArchivePage() {
  return (
    <main className="archive-page">
      <SiteHeader active="archive" />

      <section className="archive-hero">
        <div className="archive-hero-copy">
          <p className="kicker">Downs Style · 2017—2026</p>
          <h1>
            The whole history,
            <em>finally in one room.</em>
          </h1>
          <p>
            Every public post by Charles Downs is here: 258 pieces across nine
            editorial worlds. Search a subject, enter a category, or follow the
            chronology all the way back to the first candle story.
          </p>
        </div>

        <dl className="archive-hero-stats">
          <div>
            <dt>Public posts</dt>
            <dd>258</dd>
          </div>
          <div>
            <dt>Editorial categories</dt>
            <dd>09</dd>
          </div>
          <div>
            <dt>Calendar span</dt>
            <dd>10</dd>
          </div>
        </dl>
      </section>

      <section className="archive-bookends" aria-label="Archive bookends">
        <article>
          <span>Latest · August 2, 2026</span>
          <h2>Rose Water and the benefits behind our favorite flower</h2>
        </article>
        <article>
          <span>Where it began · December 4, 2017</span>
          <h2>My Favorite Candles of the Year</h2>
        </article>
      </section>

      <ArchiveExplorer
        posts={posts}
        categories={categoryCounts}
        years={years}
      />

      <footer>
        <div>
          <span className="footer-mark">DS</span>
          <p>
            Complete public archive · 258 posts.
            <br />
            Every title opens its original Downs Style page.
          </p>
        </div>
        <a href="/voice">
          See how the archive becomes a voice system <span aria-hidden="true">↗</span>
        </a>
      </footer>
    </main>
  );
}
