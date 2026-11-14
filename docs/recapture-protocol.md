# Recapture data protocol (V4 #30)

How the team makes the photos the recapture detector learns from. Team-made only: no sponsor
imagery and no renter photos ever go into training (learning-v2 L1a and L6).

## What to shoot

Each person, each phone, in each room we can stand in (dorm rooms, lounges, the venue):

| Class     | How                                                                                                                                                      | Target per person for v0 |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| `genuine` | A fresh photo of a fixed feature (window frame, door, built-in) with a 4-character code written on paper held in the frame. Vary distance, light, angle. | 40                       |
| `screen`  | A photo of a laptop or phone screen showing one of our own genuine photos or a walkthrough frame. Vary screens, angles, glare, brightness.               | 15                       |
| `print`   | A photo of a printout of one of our own photos (if a printer is available).                                                                              | 10                       |
| `paste`   | Lane D's generator makes these from genuine photos (`python -m snapback.redteam`). Do not hand-make them.                                                | 0                        |

Targets add up to about 150 genuine and 150 attacks for the team, once lane D's synthetic
attacks are counted (they are labelled `synthetic=1` and reported apart).

## Where the files go

- Name every file `<your-name>-<nnnn>.jpg` (for example `jeffrey-0001.jpg`) so file names are
  unique across the team. Convert HEIC to JPEG first.
- Genuine photos: `data/recapture/team/genuine/`. Screen and print photos:
  `data/recapture/team/attacks/`. Both git-ignored.
- One manifest row per photo in `data/recapture/team/manifest.csv`, paths relative to the
  manifest's folder:

```
path,label,source,device,room,synthetic
genuine/jeffrey-0001.jpg,genuine,jeffrey-0001,jeffrey-iphone13,dorm-a,0
attacks/jeffrey-0101.jpg,screen,jeffrey-0001,jeffrey-iphone13,dorm-a,0
```

- `source` is the file stem of the genuine photo the row comes from: a genuine photo's own stem,
  or, for an attack, the stem of the genuine photo it shows. Lane D's generator names its
  attacks the same way, so a photo and every attack made from it stay on one side of the split.
  Training stops with an error if a genuine row's source is not its own stem, or if an attack's
  source matches no genuine photo.
- `device` and `room`: the held-out set H0 is split by these (V6 `check_holdout`), so a model
  that learned a phone or a room instead of the attack is caught.

## Train and measure

```
uv run python -m snapback.redteam --src data/recapture/team/genuine --out data/redteam --seed 1
uv run python -m snapback.vision.recapture \
    --manifest data/recapture/team/manifest.csv --manifest data/redteam/manifest.csv \
    --version v0 --out data/recapture/v0.json
```

The command prints train n, dev genuine n and the frozen threshold (dev genuine false reject at
most 5%), then dev AUROC and false accept for real attacks (team captures) and, on a separate
line labelled SYNTHETIC, for lane D's generated attacks, each with its own n. Post those lines on #30. The detector runs only with
`RECAPTURE_MODEL=on` in `.env`; it can block a pass (ask for a new photo), never accuse.
