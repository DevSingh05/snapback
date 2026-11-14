import { useCallback, useEffect, useRef, useState } from "react";

// The story player: one beat on screen at a time, each with its own length. Playing, it moves to
// the next beat when the beat's time runs out and stops on the last one. A pause keeps the time
// already spent on the beat, so play picks up where it left off. With reduced motion it never
// starts on its own.

export interface StoryPlayer {
  index: number;
  playing: boolean;
  /** The last beat is on screen. */
  ended: boolean;
  /** Changes on every restart, so a beat's own animation starts over. */
  epoch: number;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  next: () => void;
  previous: () => void;
  restart: () => void;
  go: (index: number) => void;
}

export function useStoryPlayer(durations: number[], reduced: boolean): StoryPlayer {
  const last = durations.length - 1;
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(!reduced);
  const [epoch, setEpoch] = useState(0);
  // Time already spent on the beat on screen, carried across a pause.
  const spent = useRef({ index: 0, ms: 0 });

  const go = useCallback(
    (i: number) => {
      const to = Math.max(0, Math.min(last, i));
      spent.current = { index: to, ms: 0 };
      setIndex(to);
    },
    [last],
  );

  useEffect(() => {
    if (!playing || index >= last) return;
    const since = Date.now();
    const left = Math.max(0, (durations[index] ?? 0) - spent.current.ms);
    const timer = setTimeout(() => go(index + 1), left);
    return () => {
      clearTimeout(timer);
      if (spent.current.index === index) spent.current.ms += Date.now() - since;
    };
  }, [playing, index, last, durations, go, epoch]);

  const ended = index >= last;
  return {
    index,
    playing: playing && !ended,
    ended,
    epoch,
    play: () => (ended ? restartNow() : setPlaying(true)),
    pause: () => setPlaying(false),
    toggle: () => (ended ? restartNow() : setPlaying((p) => !p)),
    next: () => go(index + 1),
    previous: () => go(index - 1),
    restart: () => restartNow(),
    go,
  };

  function restartNow() {
    go(0);
    setEpoch((e) => e + 1);
    setPlaying(true);
  }
}

/** Reveals `full` a few letters at a time while playing; whole at once when paused or reduced. */
export function useTyped(full: string, playing: boolean, reduced: boolean, ms: number): string {
  const [shown, setShown] = useState(() => (playing && !reduced ? 0 : full.length));
  useEffect(() => {
    if (!playing || reduced || shown >= full.length) return;
    const tick = 30;
    const step = Math.max(1, Math.ceil(full.length / ((ms * 0.55) / tick)));
    const t = setTimeout(() => setShown((n) => Math.min(full.length, n + step)), tick);
    return () => clearTimeout(t);
  }, [playing, reduced, shown, full, ms]);
  return full.slice(0, reduced ? full.length : shown);
}

/** Counts up to `total`, one every `every` ms while playing; all at once when paused or reduced. */
export function useCount(total: number, playing: boolean, reduced: boolean, every: number): number {
  const [n, setN] = useState(() => (playing && !reduced ? 1 : total));
  useEffect(() => {
    if (!playing || reduced || n >= total) return;
    const t = setTimeout(() => setN((k) => Math.min(total, k + 1)), every);
    return () => clearTimeout(t);
  }, [playing, reduced, n, total, every]);
  return reduced ? total : n;
}
