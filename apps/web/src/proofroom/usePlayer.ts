// The replay's play clock. It walks the recorded steps (model.schedule) at real speed or
// twice that, and stops at the end. Nothing here invents a step: `at` only says how far into
// the recorded run the floor should show. With reduced motion, or a run that is still live,
// there is no clock: the floor shows everything the timeline holds.
import { useCallback, useEffect, useRef, useState } from "react";

import type { CaseTimeline } from "../contracts";
import { runLength, schedule } from "./model";

export const TICK_MS = 100;
export type Speed = 1 | 2;

export interface Player {
  at: number; // ms on the play clock; Infinity when not replaying
  playing: boolean;
  speed: Speed;
  length: number;
  replay: () => void;
  skip: () => void;
  setSpeed: (s: Speed) => void;
}

export function usePlayer(
  timeline: CaseTimeline | null,
  { auto, still }: { auto: boolean; still: boolean },
): Player {
  const live = (timeline as (CaseTimeline & { running?: boolean }) | null)?.running === true;
  const length = timeline ? runLength(schedule(timeline)) : 0;
  const key = timeline ? `${timeline.case_id}:${timeline.steps.length}` : "";
  const [at, setAt] = useState(Infinity);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(1);
  const speedRef = useRef<Speed>(1);
  speedRef.current = speed;
  const sawLive = useRef(false);
  if (live) sawLive.current = true;

  const replay = useCallback(() => {
    if (!length) return;
    setAt(0);
    setPlaying(true);
  }, [length]);
  const skip = useCallback(() => {
    setAt(Infinity);
    setPlaying(false);
  }, []);

  // A finished run plays once when it lands, unless the person watched it live or asked for
  // no motion.
  useEffect(() => {
    if (!key) return;
    if (auto && !still && !live && !sawLive.current && length > 0) {
      setAt(0);
      setPlaying(true);
    } else {
      setAt(Infinity);
      setPlaying(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, live]);

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => setAt((now) => now + TICK_MS * speedRef.current), TICK_MS);
    return () => clearInterval(timer);
  }, [playing]);

  // The end of the recording: stop, and show the whole run.
  useEffect(() => {
    if (playing && at >= length) {
      setAt(Infinity);
      setPlaying(false);
    }
  }, [playing, at, length]);

  return { at, playing, speed, length, replay, skip, setSpeed };
}
