import { useEffect, useRef, useState } from "react";

import dayBrick from "../assets/hero-day-brick.webp";
import sampleKitchen from "../assets/sample-kitchen.webp";
import sampleLivingRoom from "../assets/sample-living-room.webp";
import sampleLounge from "../assets/sample-lounge.webp";
import { Photo, State } from "../ui";
import { Lockup } from "../ui/Mark";
import { RealtorQuote } from "./RealtorQuote";
import type { HouseScene } from "./houseScene";
import type { TwinCase, TwinScene } from "./twinScene";
import "./worlds.css";

// SNAPBACK Worlds: the front door ("the outside") at "/". A drawn 3D house lifts apart on the
// page, then the check, how it works, where it helps, how a photo is placed, and three ways to
// see for yourself. The app ("the inside") is one click away at /home. Everything stamped as a
// sample is a sample; the one measured line is the app's own (Home carries the same words).

export const LANDING_HOW = [
  {
    title: "Send the ad",
    text: "Paste the link, the words or screenshots of any rental ad, or text it to SNAPBACK on iMessage.",
  },
  {
    title: "We check it against the home",
    text: "Scam-pattern rules run on any ad. Where the home has a record and a 3D scan, we check the ad against them and place its photos in the scan.",
  },
  {
    title: "Code sets the verdict",
    text: "You get a plain-words card: what matches, what does not, and what we could not check. A model can pick up to 2 extra checks and draft a next step; it never sets the verdict.",
  },
] as const;

export const LANDING_USES = [
  {
    title: "Open the city",
    text: "A map of researched places in your budget, each with its rent range.",
  },
  {
    title: "Walk it first",
    text: "Step room to room through the home's own 3D scan before you spend a day on a visit.",
  },
  { title: "Paste an ad, get the verdict", text: "One card: the place, the person and the price." },
  {
    title: "Photos from another building?",
    text: "If an ad's photos were taken somewhere else, the card says so and shows both.",
  },
] as const;

export const LANDING_MEASURED =
  "Measured on 78 real listing photos: 43 of 48 placed in the right home, 0 in the wrong one, 0 of 30 decoys fooled it";

// The measured line again, as three figures. Same numbers, same n (78 real listing photos: 48
// that belong to a home we hold, 30 decoys); the sentence under them is the source of truth.
export const LANDING_STATS = [
  { value: "43 of 48", label: "real listing photos placed in the right home" },
  { value: "0", label: "placed in the wrong home" },
  { value: "0 of 30", label: "decoy photos that fooled it" },
] as const;

// The scroll story over the pinned drawing: one short card per beat. The numbers in houseScene
// (when the floors lift, when each photo lands, when the marker goes to the sign) follow these.
export const LANDING_BEATS = [
  {
    name: "The home",
    title: "First, we open the home.",
    text: "Where a home has a 3D scan, we take it apart floor by floor and check three things: the place, the person and the price.",
  },
  {
    name: "The photos",
    title: "The ad\u2019s photos fly to where they were taken.",
    text: "Each photo is fitted to the scan. One that locks onto a wall was taken in this home. If none fit, the card says so.",
  },
  {
    name: "The record",
    title: "Then the home\u2019s own record answers.",
    text: "Is it for rent, and who may rent it out? Here the sign says for sale, with another brokerage. That is a warning on the card, never an accusation.",
  },
] as const;

const RAIL = ["The ad", ...LANDING_BEATS.map((b) => b.name)];
const FLOORS = ["The price", "The person", "The place"];
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

function Hero({ reduced }: { reduced: boolean }) {
  const stage = useRef<HTMLElement>(null);
  const pin = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const rail = useRef<HTMLOListElement>(null);
  const dot = useRef<HTMLLIElement>(null);
  const floorLbl = useRef<(HTMLDivElement | null)[]>([]);
  const signLbl = useRef<HTMLDivElement>(null);
  const scene = useRef<HouseScene | null>(null);
  const [drawn, setDrawn] = useState(true);
  // Reduced motion, or no WebGL: no pinned scroll. The drawing rests in its last frame (or is
  // absent) and the three beats sit under it as plain text.
  const still = reduced || !drawn;

  useEffect(() => {
    const cv = canvas.current;
    const el = pin.current;
    if (!cv || !el) return;
    let dead = false;
    let io: IntersectionObserver | undefined;
    void import("./houseScene").then(({ mountHouse }) => {
      if (dead) return;
      const s = mountHouse(cv, el, reduced, {
        photos: [sampleLivingRoom, sampleKitchen, sampleLounge],
        floorLabels: floorLbl.current,
        signLabel: signLbl.current,
      });
      if (!s) {
        setDrawn(false);
        return;
      }
      scene.current = s;
      io = new IntersectionObserver((es) => es.forEach((e) => s.setVisible(e.isIntersecting)));
      io.observe(el);
      window.dispatchEvent(new Event("scroll"));
    });
    return () => {
      dead = true;
      io?.disconnect();
      scene.current?.dispose();
      scene.current = null;
    };
  }, [reduced]);

  // Scroll is the clock. One passive listener, one rAF, cached measurements: nothing here reads
  // layout while scrolling, and only transforms change.
  useEffect(() => {
    const el = stage.current;
    if (!el || still || typeof ResizeObserver === "undefined") return;
    let top = 0,
      span = 1,
      track = 0,
      raf = 0,
      at = -1;
    const apply = () => {
      raf = 0;
      const p = clamp01((window.scrollY - top) / span);
      scene.current?.setProgress(p);
      if (dot.current) dot.current.style.transform = `translate3d(0,${(p * track).toFixed(1)}px,0)`;
      const k = p < 0.15 ? 0 : p < 0.44 ? 1 : p < 0.74 ? 2 : 3;
      if (k !== at && rail.current) rail.current.dataset.at = String((at = k));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(apply);
    };
    const measure = () => {
      top = el.getBoundingClientRect().top + window.scrollY;
      span = Math.max(1, el.offsetHeight - window.innerHeight);
      track = rail.current ? rail.current.offsetHeight - 10 : 0;
      onScroll();
    };
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", measure);
    // exactly one step crosses the middle line of the screen at a time: that one is "on". On a
    // phone its card sits in one slot at the bottom, so the drawing above stays clear.
    const io =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(
            (es) => es.forEach((e) => e.target.classList.toggle("is-on", e.isIntersecting)),
            { rootMargin: "-50% 0px -50% 0px" },
          );
    el.querySelectorAll(".wl-step").forEach((n) => io?.observe(n));
    el.classList.add("wl-live");
    return () => {
      io?.disconnect();
      el.classList.remove("wl-live");
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", measure);
    };
  }, [still]);

  return (
    <section
      className={still ? "wl-stage wl-still" : "wl-stage"}
      ref={stage}
      aria-label="SNAPBACK"
      data-testid="wl-stage"
    >
      <div className="wl-pin" ref={pin}>
        <canvas
          ref={canvas}
          className="wl-canvas"
          data-testid="wl-canvas"
          role="img"
          aria-label="A drawing of a house on its lot, in a block of houses, with a For sale sign in the yard. As you scroll, the floors lift apart to show the rooms, three sample photos from an ad fly in and settle on the walls they were taken at, and a gold marker goes to the yard sign. It is a drawing, not a real home. Drag to turn it."
        />
        <div className="wl-lbls" aria-hidden="true">
          {FLOORS.map((t, k) => (
            <div
              key={t}
              className="wl-lbl"
              ref={(n) => {
                floorLbl.current[k] = n;
              }}
            >
              <i />
              {t}
            </div>
          ))}
          <div className="wl-lbl wl-lbl-rec" ref={signLbl}>
            On record: for sale
          </div>
        </div>
        <ol className="wl-rail" ref={rail} data-at="0" aria-hidden="true">
          {RAIL.map((t, i) => (
            <li key={t} className="ui-mono">{`0${i}`}</li>
          ))}
          <li className="wl-rail-dot" ref={dot} />
        </ol>
      </div>
      <div className="wl-over">
        <div className="wl-step wl-step-hero">
          <div className="wl-hero-card">
            <p className="wl-eyebrow ui-mono">SNAPBACK</p>
            <h1 className="wl-h1">Trust the home, not the ad.</h1>
            <p className="wl-lede">
              Found a place online? Paste the ad. We check it against the home&rsquo;s own record
              before you pay, and say plainly what we could not check.
            </p>
            <div className="wl-acts">
              <a className="wl-btn wl-btn-main" href="/home">
                Check an ad
              </a>
              <a className="wl-btn" href="#how">
                See how it works
              </a>
            </div>
            <p className="wl-fine">
              {!drawn
                ? "The 3D drawing could not start on this device. Everything below still works."
                : reduced
                  ? "The house is a drawing, not a real home. Drag it to turn it."
                  : "The house is a drawing, not a real home. Scroll to open it, drag to turn it."}
            </p>
          </div>
        </div>
        {LANDING_BEATS.map((b, i) => (
          <div className="wl-step" key={b.name}>
            <div className="wl-say" data-testid="wl-beat">
              <p className="wl-kicker ui-mono">{`0${i + 1} · ${b.name}`}</p>
              <h2 className="wl-say-h">{b.title}</h2>
              <p className="wl-say-p">{b.text}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Verdict() {
  return (
    <section className="wl-sec wl-check" id="check" aria-labelledby="wl-check-h">
      <div className="wl-wrap wl-split">
        <div className="wl-copy">
          <p className="wl-kicker ui-mono">The check</p>
          <h2 id="wl-check-h" className="wl-h2">
            Check a rental ad before you pay.
          </h2>
          <p className="wl-p">
            Every photo in a scam ad can be real. That is the trap. So we do not judge the pictures:
            we check the ad against the home itself, and against the two rules that stop most
            losses. Never pay before a signed lease and a viewing. Never pay by Zelle, wire or gift
            card.
          </p>
          <p className="wl-fine ui-mono">
            SYNTHETIC: a test ad we wrote to show the card. No real home, person or phone number.
          </p>
        </div>
        <article className="wl-card" data-testid="wl-verdict" aria-label="Sample verdict card">
          <header className="wl-card-band">
            <span className="wl-card-meta ui-mono">Sample case · SYNTHETIC</span>
            <h3 className="wl-card-head">
              Hold off: it asks for money before you&rsquo;ve seen the place
            </h3>
          </header>
          <ul className="wl-rows">
            <li>
              <span className="wl-row-k ui-mono">The price</span>
              <span className="wl-row-t">Asks for a deposit by Zelle before any viewing.</span>
              <State kind="warn" />
            </li>
            <li>
              <span className="wl-row-k ui-mono">The person</span>
              <span className="wl-row-t">
                The number is not the leasing office&rsquo;s number on record.
              </span>
              <State kind="unconfirmed" />
            </li>
            <li>
              <span className="wl-row-k ui-mono">The place</span>
              <span className="wl-row-t">
                No scan in this sample, so the photos were not placed.
              </span>
              <State kind="unchecked" />
            </li>
          </ul>
          <p className="wl-card-foot">
            A number that is not the office&rsquo;s never marks anyone a scammer: it reads Not
            confirmed. Call the office on record before you send anything.
          </p>
        </article>
      </div>
    </section>
  );
}

// A small drawn specimen over each step, so the three steps show the thing rather than only
// say it: the ad as it arrives, the home's floors under the scan line, the three row states.
// Decorative (the words beside them carry the meaning), and stamped as a sample.
function HowSpecimen({ step }: { step: number }) {
  if (step === 0)
    return (
      <span className="wl-spec wl-spec-ad" aria-hidden="true">
        <span className="wl-spec-tag ui-mono">Sample ad</span>
        <span className="wl-spec-bubble">
          <i />
          <i />
          <b>&ldquo;Deposit tonight by Zelle&rdquo;</b>
        </span>
        <span className="wl-spec-send">Check it</span>
      </span>
    );
  if (step === 1)
    return (
      <span className="wl-spec wl-spec-scan" aria-hidden="true">
        <span className="wl-spec-tag ui-mono">Drawing</span>
        <svg viewBox="44 4 112 88" focusable="false">
          <path className="wl-spec-roof" d="M56 30 100 8l44 22z" />
          <path className="wl-spec-floor" d="M62 30h76v18H62zM62 52h76v18H62zM62 74h76v14H62z" />
          <path
            className="wl-spec-win"
            d="M72 35h12v9H72zM116 35h12v9h-12zM72 57h12v9H72zM94 76h12v12H94z"
          />
          <path className="wl-spec-ground" d="M20 88h160" />
        </svg>
        <span className="wl-spec-line" />
      </span>
    );
  return (
    <span className="wl-spec wl-spec-states" aria-hidden="true">
      <span className="wl-spec-tag ui-mono">Sample card</span>
      <State kind="ok" />
      <State kind="mismatch" />
      <State kind="unchecked" />
    </span>
  );
}

function How() {
  return (
    <section className="wl-sec wl-band" id="how" aria-labelledby="wl-how-h">
      <div className="wl-wrap">
        <p className="wl-kicker ui-mono">How it works</p>
        <h2 id="wl-how-h" className="wl-h2">
          Three steps. Code decides.
        </h2>
        <ol className="wl-how">
          {LANDING_HOW.map((s, i) => (
            <li key={s.title}>
              <HowSpecimen step={i} />
              <span className="wl-how-n ui-mono">{`0${i + 1}`}</span>
              <b>{s.title}</b>
              <span>{s.text}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Uses() {
  return (
    <section className="wl-sec" id="use" aria-labelledby="wl-use-h">
      <div className="wl-wrap wl-split wl-split-photo">
        <figure className="wl-bigphoto">
          <Photo
            src={dayBrick}
            alt="A brick apartment building with balconies, seen from the street in daylight"
            stamp="sample"
            hero
          />
          <figcaption className="wl-fine">
            Sample photo by Seb Doe on Unsplash. It is not a home we check.
          </figcaption>
        </figure>
        <div className="wl-copy">
          <p className="wl-kicker ui-mono">How you can use it</p>
          <h2 id="wl-use-h" className="wl-h2">
            In the order a renter meets it.
          </h2>
          <ol className="wl-uses">
            {LANDING_USES.map((u, i) => (
              <li key={u.title}>
                <b className="wl-use-n" aria-hidden="true">
                  {i + 1}
                </b>
                <span>
                  <strong>{u.title}</strong>
                  <span>{u.text}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

// The sample for "Taken here": two photos that fit the drawn floor and one from another home.
// The poses and point counts are part of the drawing (SYNTHETIC), never a measurement.
const TWIN = [
  {
    name: "Photo 1",
    src: sampleLivingRoom,
    alt: "A living room with a grey sofa and plants",
    fits: true,
    where: "Living room, facing the window.",
    C: [6.3, 1.42, 0.05],
    A: [6.3, 1.42, 5.25],
    w: 3.45,
    h: 2.3,
    ry: 0,
    n: 457,
  },
  {
    name: "Photo 2",
    src: sampleKitchen,
    alt: "A kitchen with counters along one wall",
    fits: true,
    where: "Kitchen, facing the counters.",
    C: [0.68, 1.3, 4.55],
    A: [3.1, 1.3, 4.55],
    w: 2.4,
    h: 1.6,
    ry: Math.PI / 2,
    n: 312,
  },
  {
    name: "Another home",
    src: sampleLounge,
    alt: "A different living room, with a pale green sofa",
    fits: false,
    where: "No room in this home lines up.",
    n: 0,
  },
] as const satisfies readonly (TwinCase & { name: string; alt: string; where: string })[];

const TWIN_FIRST = TWIN[0];

function TakenHere({ reduced }: { reduced: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const camLbl = useRef<HTMLDivElement>(null);
  const wallLbl = useRef<HTMLDivElement>(null);
  const count = useRef<HTMLSpanElement>(null);
  const picks = useRef<(HTMLButtonElement | null)[]>([]);
  const scene = useRef<TwinScene | null>(null);
  const [drawn, setDrawn] = useState(true);
  const [at, setAt] = useState(0);
  const [wait, setWait] = useState(false);
  const cur = TWIN[at] ?? TWIN_FIRST;

  const play = (i: number) => {
    setAt(i);
    const s = scene.current;
    if (!s) return;
    setWait(true);
    const thumb = picks.current[i]?.querySelector("img")?.getBoundingClientRect() ?? null;
    s.play(i, thumb, () => setWait(false));
  };
  const playRef = useRef(play);
  playRef.current = play;

  useEffect(() => {
    const cv = canvas.current;
    const el = box.current;
    if (!cv || !el || typeof IntersectionObserver === "undefined") return;
    let dead = false;
    let io: IntersectionObserver | undefined;
    let started = false;
    // the scene is fetched only when the section is near the screen
    const near = new IntersectionObserver(
      (es) => {
        if (!es.some((e) => e.isIntersecting)) return;
        near.disconnect();
        void import("./twinScene").then(({ mountTwin }) => {
          if (dead) return;
          const s = mountTwin(cv, el, reduced, TWIN as readonly TwinCase[], {
            cam: camLbl.current,
            wall: wallLbl.current,
            count: count.current,
          });
          if (!s) {
            setDrawn(false);
            return;
          }
          scene.current = s;
          io = new IntersectionObserver(
            (xs) =>
              xs.forEach((e) => {
                s.setVisible(e.isIntersecting);
                // the first photo flies in once, when half the drawing is on screen
                if (!started && e.intersectionRatio >= 0.5) {
                  started = true;
                  playRef.current(0);
                }
              }),
            { threshold: [0, 0.5] },
          );
          io.observe(el);
        });
      },
      { rootMargin: "600px 0px" },
    );
    near.observe(el);
    return () => {
      dead = true;
      near.disconnect();
      io?.disconnect();
      scene.current?.dispose();
      scene.current = null;
    };
  }, [reduced]);

  return (
    <section className="wl-sec wl-band wl-taken" id="taken" aria-labelledby="wl-taken-h">
      <div className="wl-wrap">
        <p className="wl-kicker ui-mono">Taken here</p>
        <h2 id="wl-taken-h" className="wl-h2">
          We find which home the ad&rsquo;s photos were taken in.
        </h2>
        <div className="wl-twin">
          <div className={drawn ? "wl-twin-stage" : "wl-twin-stage wl-twin-off"} ref={box}>
            <canvas
              ref={canvas}
              className="wl-canvas"
              data-testid="wl-twin"
              role="img"
              aria-label="One floor of a scanned home, cut open, as a drawing. The ad's photo flies in and settles where it was taken: a camera marker stands on the floor and lines join points in the photo to the same points on the wall. A photo from another home is tried against each room and turned away. It is a drawn sample, not a real home."
            />
            <div className="wl-lbl wl-lbl-c" ref={camLbl} aria-hidden="true">
              Camera stood here
            </div>
            <div className="wl-lbl wl-lbl-c wl-lbl-ok" ref={wallLbl} aria-hidden="true">
              <span ref={count}>0</span> points line up
            </div>
            <span className="wl-twin-tag ui-mono">Drawn sample · SYNTHETIC</span>
          </div>
          <div className="wl-twin-side">
            <div className="wl-res" aria-live="polite" data-testid="wl-res">
              <p className="wl-res-big">
                {wait
                  ? cur.fits
                    ? "Fitting it in"
                    : "Trying every room"
                  : cur.fits
                    ? "Taken here"
                    : "Not taken here"}
              </p>
              <p className="wl-res-where">{wait ? "\u00a0" : cur.where}</p>
              <p className="wl-res-meta" data-wait={wait || undefined}>
                <State kind={cur.fits ? "ok" : "mismatch"} />
                <span>
                  {cur.fits
                    ? `${cur.n} points line up with the scan in this drawn sample.`
                    : "0 points line up in this drawn sample."}
                </span>
              </p>
            </div>
            <div className="wl-pick" role="group" aria-label="Pick a photo from the ad">
              {TWIN.map((c, i) => (
                <button
                  key={c.name}
                  type="button"
                  aria-pressed={i === at}
                  ref={(n) => {
                    picks.current[i] = n;
                  }}
                  onClick={() => play(i)}
                >
                  <img src={c.src} alt={c.alt} loading="lazy" />
                  <span>{c.name}</span>
                </button>
              ))}
            </div>
            <p className="wl-fine">
              {drawn
                ? "Pick a photo to send it into the scan. Drag the scan to turn it."
                : "The 3D drawing could not start on this device."}
            </p>
          </div>
        </div>
        <dl className="wl-stats" data-testid="wl-stats">
          {LANDING_STATS.map((x) => (
            <div key={x.label}>
              <dt>{x.label}</dt>
              <dd>{x.value}</dd>
            </div>
          ))}
        </dl>
        <p className="wl-measured" data-testid="wl-measured">
          <b className="wl-tag-live ui-mono">LIVE</b>, re-measured Nov 15 · {LANDING_MEASURED}
        </p>
        <p className="wl-fine">
          The floor and the three pictures are stand-ins for the sample (SYNTHETIC), and say so. In
          the app the photos come from the ad and the scan is the building&rsquo;s real one, stamped
          LIVE.
        </p>
      </div>
    </section>
  );
}

function SeeForYourself() {
  return (
    <section className="wl-sec" id="see" aria-labelledby="wl-see-h">
      <div className="wl-wrap">
        <p className="wl-kicker ui-mono">See it for yourself</p>
        <h2 id="wl-see-h" className="wl-h2">
          Check all three before you trust us.
        </h2>
        <a className="wl-spot" href="/spot" data-testid="wl-col-spot">
          <span className="wl-spot-k ui-mono">30 seconds</span>
          <span className="wl-spot-t">Spot the scam in 30 seconds</span>
          <span className="wl-spot-p">
            A quick game first: can you spot the scam ad before the clock runs out?
          </span>
          <span className="wl-spot-go" aria-hidden="true">
            Play
          </span>
        </a>
        <div className="wl-three">
          <div className="wl-col" data-testid="wl-col-stories">
            <h3 className="wl-h3">Stories</h3>
            <p className="wl-p">
              Three renters&rsquo; stories, played out on the real app with sample data. Press play,
              or step through by hand.
            </p>
            <a className="wl-btn wl-btn-main" href="/stories">
              Watch a story
            </a>
          </div>
          <div className="wl-col" data-testid="wl-col-reviews">
            <h3 className="wl-h3">Reviews &amp; reports</h3>
            <p className="wl-p">
              What people who tried SNAPBACK said, counted with the number of people stated. And a
              full sample report you can open.
            </p>
            <div className="wl-acts">
              <a className="wl-btn wl-btn-main" href="/reviews">
                Read the reviews
              </a>
              <a className="wl-btn" href="/case/7Q2M">
                Open a sample report
              </a>
            </div>
            <RealtorQuote />
          </div>
          <div className="wl-col" data-testid="wl-col-app">
            <h3 className="wl-h3">Your own ad</h3>
            <p className="wl-p">
              The quickest proof is your own listing. Paste it into the one box and read the card.
            </p>
            <a className="wl-btn wl-btn-main" href="/home">
              Open SNAPBACK
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function WorldsLanding() {
  const [reduced] = useState(
    () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
  );
  return (
    <div className="wl" data-testid="worlds-landing">
      <header className="wl-bar">
        <div className="wl-bar-in">
          <a className="wl-mark" href="/" aria-label="SNAPBACK">
            <Lockup />
          </a>
          <nav className="wl-nav" aria-label="Sections">
            <a href="#how">How it works</a>
            <a href="#use">How you use it</a>
            <a href="#taken">Taken here</a>
            <a href="/stories">Stories</a>
            <a href="/reviews">Reviews</a>
          </nav>
          <a className="wl-btn wl-btn-main wl-open" href="/home">
            Open SNAPBACK
          </a>
        </div>
      </header>
      <main>
        <Hero reduced={reduced} />
        <Verdict />
        <How />
        <Uses />
        <TakenHere reduced={reduced} />
        <SeeForYourself />
      </main>
      <footer className="wl-foot">
        <div className="wl-wrap">
          <p>
            SNAPBACK never messages anyone for you and never asks for money. Code sets every
            verdict. A model picks up to 2 extra checks and drafts a next step it never sends; it
            never sets the verdict. Every number here says how many it counts and whether it is
            live, a fixture or synthetic.
          </p>
          <p className="wl-fine">
            Sample photos by Seb Doe, Collov Home Design and Minh Pham on Unsplash. They are not the
            homes we check.
          </p>
        </div>
      </footer>
    </div>
  );
}
