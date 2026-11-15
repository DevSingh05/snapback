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
`detect.py` uses for "flagged"). The three columns are the shipped finder, the finder with the
phone and photo-copy fallback (`find_rings(hop=True)`, off by default), and a keyword search for
payment words grouped by exact phone or photo (the baseline).

| Variant (SYNTHETIC, n = 10 rings) | Shipped finder | With phone/photo fallback | Keyword baseline | Honest ads flagged |
|---|---|---|---|---|
| Original wording | 10 of 10 | 10 of 10 | 1 of 10 | 0 of 2,684 |
| Reworded | 7 of 10 | 9 of 10 | 0 of 10 | 0 of 2,684 |
| Reworded, ring photos re-shot (stress) | 1 of 10 | 7 of 10 | 0 of 10 | 0 of 2,684 |
| Reworded, phones and photos hidden (stress) | 0 of 10 | 0 of 10 | 0 of 10 | 0 of 2,684 |

Read this honestly:

- The finder does not hold up fully. Rewording alone costs it 3 of 10 rings. Most rewritten asks
  stop marking their ad as payment-first, so the ads are no longer seeds, and a ring with few
  seeds falls apart. The phone and photo links still join the ads that stay marked, which is why most rings
  survive at the 4-ad bar.
- The fallback is the cheapest signal already in the code: an ad one exact link from a seed (same
  phone, or a repost of a seed's photos under another number) becomes a seed too. It recovers
  2 of the 3 lost rings and adds no false flag on this corpus. It is off by default; turning it on
  is a product call, because an honest ad that shares a phone with a scammer would be pulled in.
- If an operator also re-shoots photos, 7 of 10 rings remain with the fallback, 1 of 10 without.
  Wording alone (phones and photos hidden) finds none, even on the original text: the wording signal
  needs the other links to form a ring.
- Ad-level recall is the weaker number. Ring ads flagged: 329 of 355 on the original wording,
  70 of 355 (20 percent) reworded with the shipped finder, 171 of 355 (48 percent) with the
  fallback. "Found" is a lenient bar (4 ads); read 7 or 9 of 10 as "the ring is seen", not "every
  ad is caught". At the ad level the shipped finder does collapse under rewording.
- Every false-flag count is on the same 2,684 honest ads, which include a property manager with
  many ads on one number and honest relists with shared photos. Zero is a result on this
  generator, not a guarantee on real ads.

An optional LIVE variant (`--live`) asks a hosted model to reword the ask sentences. It runs only
when `ANTHROPIC_API_KEY` is already in the environment, never prints it, is labelled LIVE in the
JSON and is not run in CI. It has not been run for the numbers above.

Tests: `tests/test_forensics_paraphrase.py` (the full results are regenerated and compared with the
committed file). The Arlequin view shows the reworded line from this file.
