# Forensics robustness eval (SYNTHETIC data only)

## Reworded ads: does the ring finder still link a ring?

    PYTHONPATH=src uv run python -m snapback.forensics.paraphrase

Writes `eval/forensics/paraphrase_results.json`. The data is the SYNTHETIC 90-day stream
(`snapback.forensics.stream`, seed 20261115): n = 3,039 ads, 10 seeded rings with 355 ring ads,
2,684 honest ads. No real ad, phone or photo.

The attack is a deterministic rewrite (one RNG per ad, so CI gets the same bytes): every payment-first
sentence in a ring ad is rebuilt from parts, the pretext line and sign-off come from a larger pool,
other sentences are reordered and lightly reworded, and prices are reformatted (none occur in the
corpus; covered by a unit test). Phones and photo ids do not change, because rewording does not
change them. Identical payment-first sentences between two ads of one ring fall from 6.3 percent of
pairs to 0.0 percent.

"Found" means at least 4 of a ring's ads sit in the groups the finder reports (the bar
`detect.py` uses for "flagged"). Columns: the shipped finder (phone and photo-copy fallback on,
`find_rings(hop=True)`, the default), the same finder seeded by wording only (`hop=False`), and a
keyword search for payment words grouped by exact phone or photo (the baseline).

| Variant (SYNTHETIC, n = 10 rings) | Shipped finder | Wording-only seeds | Keyword baseline | Honest ads flagged (shipped) |
|---|---|---|---|---|
| Original wording | 10 of 10 | 10 of 10 | 1 of 10 | 0 of 2,684 |
| Reworded | 9 of 10 | 7 of 10 | 0 of 10 | 0 of 2,684 |
| Reworded, ring photos re-shot (stress) | 7 of 10 | 1 of 10 | 0 of 10 | 0 of 2,684 |
| Reworded, phones and photos hidden (stress) | 0 of 10 | 0 of 10 | 0 of 10 | 0 of 2,684 |

Read this honestly:

- The finder does not hold up fully. Rewording costs the wording-only seeds 3 of 10 rings (1 with the fallback). Most rewritten asks
  stop marking their ad as payment-first, so the ads are no longer seeds, and a ring with few
  seeds falls apart. The phone and photo links still join the ads that stay marked, which is why most rings
  survive at the 4-ad bar.
- The fallback is the cheapest signal already in the code: an ad one exact link from a seed (same
  phone, or a repost of a seed's photos under another number) becomes a seed too. It is now on by
  default. It recovers 2 of the 3 rings that rewording costs and adds no false flag on this corpus.
  Its risk: an honest ad that shares a phone with a scammer would be pulled in.
- If an operator also re-shoots photos, 7 of 10 rings remain with the fallback on, 1 of 10 without.
  Wording alone (phones and photos hidden) finds none, even on the original text: the wording signal
  needs the other links to form a ring.
- Ad-level recall is the weaker number. Ring ads flagged (shipped finder): 354 of 355 on the
  original wording, 171 of 355 (48 percent) reworded. With wording-only seeds: 329 and 70 of 355
  (20 percent). "Found" is a lenient bar (4 ads); read 9 of 10 as "the ring is seen", not "every
  ad is caught". At the ad level the finder loses about half the ring under rewording.
- Every false-flag count is on the same 2,684 honest ads, which include a property manager with
  many ads on one number and honest relists with shared photos. Zero is a result on this
  generator, not a guarantee on real ads.

An optional LIVE variant (`--live`) asks a hosted model to reword the ask sentences. It runs only
when `ANTHROPIC_API_KEY` is already in the environment, never prints it, is labelled LIVE in the
JSON and is not run in CI. It has not been run for the numbers above.

Tests: `tests/test_forensics_paraphrase.py` (the full results are regenerated and compared with the
committed file). The Arlequin view shows the reworded line from this file.
