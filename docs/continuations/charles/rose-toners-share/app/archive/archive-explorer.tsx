"use client";

import { useMemo, useState } from "react";

export type ArchivePost = {
  publishedDate: string;
  year: string;
  category: string;
  title: string;
  url: string;
  author: string;
  wordCount: number;
};

type CategoryCount = {
  label: string;
  count: number;
};

const monthNames = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function formatDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return `${monthNames[month - 1]} ${day}, ${year}`;
}

export function ArchiveExplorer({
  posts,
  categories,
  years,
}: {
  posts: ArchivePost[];
  categories: CategoryCount[];
  years: string[];
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [year, setYear] = useState("All");

  const filteredPosts = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return posts.filter((post) => {
      const matchesQuery =
        !needle ||
        `${post.title} ${post.category}`.toLowerCase().includes(needle);
      const matchesCategory =
        category === "All" || post.category === category;
      const matchesYear = year === "All" || post.year === year;
      return matchesQuery && matchesCategory && matchesYear;
    });
  }, [category, posts, query, year]);

  const resetFilters = () => {
    setQuery("");
    setCategory("All");
    setYear("All");
  };

  return (
    <section className="archive-explorer" aria-labelledby="archive-results">
      <div className="archive-toolbar">
        <label className="archive-search">
          <span>Search the archive</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Try candles, cotton, rose…"
          />
        </label>

        <label className="archive-year">
          <span>Year</span>
          <select value={year} onChange={(event) => setYear(event.target.value)}>
            <option value="All">All years</option>
            {years.map((item) => (
              <option value={item} key={item}>
                {item}
              </option>
            ))}
          </select>
        </label>

        <div className="archive-result-count" aria-live="polite">
          <strong>{filteredPosts.length}</strong>
          <span>{filteredPosts.length === 1 ? "post" : "posts"} in view</span>
        </div>
      </div>

      <div className="archive-category-strip" aria-label="Filter by category">
        <button
          type="button"
          className={category === "All" ? "is-active" : undefined}
          aria-pressed={category === "All"}
          onClick={() => setCategory("All")}
        >
          <span>All rooms</span>
          <strong>{posts.length}</strong>
        </button>
        {categories.map((item) => (
          <button
            type="button"
            className={category === item.label ? "is-active" : undefined}
            aria-pressed={category === item.label}
            onClick={() => setCategory(item.label)}
            key={item.label}
          >
            <span>{item.label}</span>
            <strong>{item.count}</strong>
          </button>
        ))}
      </div>

      <div className="archive-results-heading">
        <div>
          <p className="kicker">The complete public record</p>
          <h2 id="archive-results">Every post, newest first.</h2>
        </div>
        {query || category !== "All" || year !== "All" ? (
          <button type="button" onClick={resetFilters}>
            Clear filters
          </button>
        ) : null}
      </div>

      {filteredPosts.length ? (
        <div className="archive-list">
          {filteredPosts.map((post, index) => (
            <article
              className="archive-entry"
              data-archive-entry
              key={post.url}
            >
              <span className="archive-index">
                {String(index + 1).padStart(3, "0")}
              </span>
              <div className="archive-entry-copy">
                <p>
                  <span>{post.category}</span>
                  <time dateTime={post.publishedDate}>
                    {formatDate(post.publishedDate)}
                  </time>
                </p>
                <h3>
                  <a href={post.url} target="_blank" rel="noreferrer">
                    {post.title}
                    <span aria-hidden="true">↗</span>
                  </a>
                </h3>
              </div>
              <span className="archive-word-count">
                {post.wordCount.toLocaleString("en-US")} words
              </span>
            </article>
          ))}
        </div>
      ) : (
        <div className="archive-empty">
          <p>No post matches that combination yet.</p>
          <button type="button" onClick={resetFilters}>
            Return to the full archive
          </button>
        </div>
      )}
    </section>
  );
}
