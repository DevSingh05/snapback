# Replays (D8, #71)

Real reported rental scams, re-created as staged cases and run through SNAPBACK. A replay shows
only checks SNAPBACK has today: every finding is a line copied from the card the code produces
for the replay's own case (`fixtures/demo/replay-<slug>/`), and a test re-runs each case and
compares. No victim names, no addresses. Each says plainly what SNAPBACK cannot catch.

## 1. A Zelle deposit for a real house that was never for rent (PRICE)

- **Source:** Los Angeles Times, 2026-07-31,
  https://www.latimes.com/california/story/2026-07-31/online-rental-scams-sweeping-social-media
- **Story (3 lines):** A real house is listed for rent; the owner still lives there and never
  offered it. The poster cannot show it "for weeks" and sends a professional video tour instead.
  The renter pays a $75 fee, then a $2,500 deposit by Zelle; the poster disappears. $2,575 lost.
- **SNAPBACK:** Hold off, before the payment. The photos were taken in this house, nobody has
  proved they are inside, the right to rent is not shown, and a Zelle deposit before a viewing
  is a red flag.
- **Can't catch:** SNAPBACK does not open the video tour link, so it cannot tell the tour was
  copied from an older listing. Real photos of a real house do not show the poster may rent it.
- **Replay:** `demo/replays/zelle-deposit-real-house-video-tour.json`

## Parked

- **Door code, owner of record differs (PERSON).** ABC13 Houston, 2025-02-15. The renter moved
  in on Saturday Feb 8 and was told on "the following Monday" (2 days later) that the poster did
  not own the house. Parked until A19 #140 and D12 #160 merge, so the owner-of-record line comes
  from code. The source house is in Montgomery County and D12 reads Harris County (HCAD), so
  it will be re-created on a kit Harris County house. Can't catch: a door-code holder passes
  the presence check (red team H1).
- **Photos of a different apartment (PLACE).** BBB scam study "Is that rental listing real?".
  The page is undated; it will carry the source's own date once one is found, never an invented
  one.
