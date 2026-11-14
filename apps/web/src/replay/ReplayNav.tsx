import { FEATURED_REPLAY_SLUG } from "./index";
import { replayLang, words } from "./text";
import { useReplays } from "./useReplays";
import "./replay.css";

// The header tab for the demo's real case. If its replay file is absent it opens the index.
export function ReplayNav() {
  const replays = useReplays();
  const lang = replayLang();
  const featured = replays.some((r) => r.slug === FEATURED_REPLAY_SLUG);
  return (
    <nav className="site-nav" aria-label="Demo">
      <a href="/replay">{words(lang).navAll}</a>
      <a className="site-nav-case" href={featured ? `/replay/${FEATURED_REPLAY_SLUG}` : "/replay"}>
        {words(lang).navCase}
      </a>
    </nav>
  );
}
