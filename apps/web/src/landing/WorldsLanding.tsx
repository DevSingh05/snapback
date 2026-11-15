import { useEffect, useRef, useState } from "react";

import dayBrick from "../assets/hero-day-brick.webp";
import sampleLivingRoom from "../assets/sample-living-room.webp";
import sampleLounge from "../assets/sample-lounge.webp";
import { Photo, PhotoPin, State } from "../ui";
import { Lockup } from "../ui/Mark";
import { RealtorQuote } from "./RealtorQuote";
import type { HouseScene } from "./houseScene";
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
    text: "You get a plain-words card: what matches, what does not, and what we could not check. A model only explains it; it never sets it.",
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

function Hero({ reduced }: { reduced: boolean }) {
  const stage = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<HouseScene | null>(null);
  const [drawn, setDrawn] = useState(true);

  useEffect(() => {
    const cv = canvas.current;
    const el = stage.current;
    if (!cv || !el) return;
    let dead = false;
    let io: IntersectionObserver | undefined;
    void import("./houseScene").then(({ mountHouse }) => {
      if (dead) return;
      const s = mountHouse(cv, el, reduced);
      if (!s) {
        setDrawn(false);
        return;
      }
      scene.current = s;
      io = new IntersectionObserver((es) => es.forEach((e) => s.setVisible(e.isIntersecting)));
      io.observe(el);
    });
    return () => {
      dead = true;
      io?.disconnect();
      scene.current?.dispose();
      scene.current = null;
    };
  }, [reduced]);

  return (
    <section className="wl-hero" ref={stage} aria-label="SNAPBACK">
      <canvas
        ref={canvas}
        className="wl-canvas"
        data-testid="wl-canvas"
        role="img"
        aria-label="A drawing of a house on its lot, in a block of houses. The floors lift apart to show the rooms, and a band of scan points sweeps up through them. It is a drawing, not a real home. Drag to turn it."
      />
      <div className="wl-hero-card">
        <p className="wl-eyebrow ui-mono">SNAPBACK</p>
        <h1 className="wl-h1">Trust the home, not the ad.</h1>
        <p className="wl-lede">
          Found a place online? Paste the ad. We check it against the home&rsquo;s own record before
          you pay, and say plainly what we could not check.
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
          {drawn
            ? "The house is a drawing, not a real home. Drag it to turn it."
            : "The 3D drawing could not start on this device. Everything below still works."}
        </p>
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

function TakenHere() {
  return (
    <section className="wl-sec wl-band wl-taken" id="taken" aria-labelledby="wl-taken-h">
      <div className="wl-wrap">
        <p className="wl-kicker ui-mono">Taken here</p>
        <h2 id="wl-taken-h" className="wl-h2">
          We find which home the ad&rsquo;s photos were taken in.
        </h2>
        <div className="wl-pair">
          <div>
            <Photo
              src={sampleLounge}
              alt="The ad's photo: a living room with a pale green sofa"
              stamp="sample"
            >
              <PhotoPin n={1} x={38} y={56} />
              <PhotoPin n={2} x={66} y={34} />
            </Photo>
            <p className="wl-cap ui-mono">The ad&rsquo;s photo</p>
          </div>
          <div>
            <Photo
              src={sampleLivingRoom}
              alt="The same view found in the building's 3D scan: a living room with a grey sofa and plants, standing in for the scan"
              stamp="sample"
            >
              <PhotoPin n={1} x={38} y={56} />
              <PhotoPin n={2} x={66} y={34} />
            </Photo>
            <p className="wl-cap ui-mono">Found in the building&rsquo;s scan (stand-in)</p>
          </div>
        </div>
        <p className="wl-measured ui-mono" data-testid="wl-measured">
          MEASURED, re-measured Nov 15 · {LANDING_MEASURED}
        </p>
        <p className="wl-fine">
          Both pictures are stock stand-ins for the sample, and say so. In the app the pair comes
          from the ad and the building&rsquo;s real scan, stamped LIVE.
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
        <TakenHere />
        <SeeForYourself />
      </main>
      <footer className="wl-foot">
        <div className="wl-wrap">
          <p>
            SNAPBACK never messages anyone for you and never asks for money. Code sets every
            verdict; a model only explains it. Every number here says how many it counts and whether
            it is live, a fixture or synthetic.
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
