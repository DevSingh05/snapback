import { SourceChip } from "../components/SourceChip";
import { Wordmark } from "../components/HouseGlyph";
import { KitArt } from "../components/KitArt";
import { PATTERN_ART } from "./ReplayPage";
import { replayLang, shortDate, words, type Lang } from "./text";
import { useReplays } from "./useReplays";
import type { Replay } from "./types";
import "./replay.css";

export function ReplayIndexView({
  replays,
  lang = replayLang(),
}: {
  replays: Replay[];
  lang?: Lang;
}) {
  const t = words(lang);
  return (
    <article className="replay-page replay-index">
      <header className="replay-head">
        <div className="replay-masthead">
          <Wordmark />
          <SourceChip source="fixture" />
        </div>
        <h1>{t.indexTitle}</h1>
        <p className="replay-source">{t.indexLead}</p>
      </header>
      <ul className="replay-list" data-testid="replay-list">
        {replays.map((r) => (
          <li key={r.slug} data-slug={r.slug}>
            <KitArt kind={PATTERN_ART[r.pattern]} className="replay-list-art" detail="low" />
            <span className="replay-pattern">{t.pattern[r.pattern]}</span>
            <h2>
              <a href={`/replay/${r.slug}`}>{r.title}</a>
            </h2>
            {r.source && !r.fictional ? (
              <p className="replay-source">
                {/* Plain text, no link: a public report can print a renter's name. */}
                {t.source}: {r.source.name}
                {", "}
                {shortDate(r.source.published_on, lang)}
              </p>
            ) : (
              <p className="replay-source">{t.fictional}</p>
            )}
          </li>
        ))}
      </ul>
    </article>
  );
}

export function ReplayIndexPage() {
  return <ReplayIndexView replays={useReplays()} />;
}
