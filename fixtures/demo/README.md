# Demo case pack (A9)

Three staged cases that each run end to end to a card. In the demo it is a
**staged poster, real CoStar records**: the listing is written by us, playing the poster, and
the building records are the sponsor's, read from the kit at run time.

**Every one of these is a staged example, and says so.** Each card made from this pack carries
"Staged example. The SNAPBACK team wrote this listing to show the checks. It is not a real
poster." first in its footer, on the web, in the picture and in the printed output. These are
not replays of reported cases: the sourced replays (D8, #71) get their own
`fixtures/demo/replay-*` folders next to these.

Nothing of the sponsor's is in this folder. What is here is the staged listing for each case
and a synthetic stand-in for everything the live run reads from the kit or the twin: the
record, where the photos were placed, and the reply to the challenge. Ids start with `fx-`,
phone numbers are 555-01xx, and web addresses end in `.example`. With these the same three
cases run on any machine, labelled FIXTURE.

| Case | What the poster did                                                                                                                                                                                                                                    | What the card says                                                                                                                                                            |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `a`  | Real photos of a real building. The unit is not on the record, the rent is far under the band for that size, the phone is not the leasing office, the link imitates the building's site, and the proof-of-presence reply is a copy of listing photo 2. | Don't pay: the reply is a copy of a listing photo. Every other finding is on its row.                                                                                         |
| `b`  | The same listing, but one of its three photos was taken in a different building.                                                                                                                                                                       | Don't pay: a photo was taken in a different property.                                                                                                                         |
| `c`  | A house that is for sale, posted as a rental. There is no 3D scan of it.                                                                                                                                                                               | Hold off: the house is listed for sale, not for rent. For sale is a red flag, not proof, so it is not "don't pay"; and it is said first even though no photo could be placed. |

**What `DEMO_CASE` does depends on the data source.**

- **With `SNAPBACK_DATA_SOURCE=fixture`** (the default) it runs on the stand-ins in this
  folder and does not read the kit. The record on each card is the synthetic one here, the
  card is labelled FIXTURE, and the three cases come out as in the table above.
- **With `SNAPBACK_DATA_SOURCE=live`** it supplies only the listing text. No stand-in from
  this folder is used: a live case never carries one. The photo and presence lines read "Not
  checked", so case `a` comes out "could not place the photos" and LIVE, not "don't pay". The
  server logs a warning at start when both are set, so this is not a surprise on demo day.
- **A `property_id` sent in fixture mode** makes the check use that record from lane D's
  synthetic kit with the shared stand-ins for the twin and the challenge, not this pack's.

**What `DEMO_CASE` does depends on the data source.**

- **With `SNAPBACK_DATA_SOURCE=fixture`** (the default) it runs on the stand-ins in this
  folder and does not read the kit. The record on each card is the synthetic one here, the
  card is labelled FIXTURE, and the three cases come out as in the table above.
- **With `SNAPBACK_DATA_SOURCE=live`** it supplies only the listing text. No stand-in from
  this folder is used: a live case never carries one. The photo and presence lines read "Not
  checked", so case `a` comes out "could not place the photos" and LIVE, not "don't pay". The
  server logs a warning at start when both are set, so this is not a surprise on demo day.
- **A `property_id` sent in fixture mode** makes the check use that record from lane D's
  synthetic kit with the shared stand-ins for the twin and the challenge, not this pack's.

## Run them

```
uv run python -m snapback.agent.demo        # prints all three cards
DEMO_CASE=a make api                        # the API runs every new check on case a
```

With `DEMO_CASE` set, a check started with no text reads the staged listing in `listing.txt`.
Text the presenter pastes is read instead: against the same stand-ins in fixture mode, and
with no stand-in at all in live mode.

## Files in each case

- `listing.txt`: the staged poster's message, as a renter would paste it.
- `case.json`: a title, and the for-sale lookup result if there is one.
- `property_record.json`: the stand-in record. The office phone is kept only as a hash.
- `module_evidence.json`: where the photos were placed and how the challenge went.
- `spot_ranking.json`: the spots a challenge may name.
