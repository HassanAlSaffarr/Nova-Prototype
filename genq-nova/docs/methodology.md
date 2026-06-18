# How Nova Detects Change

This explains how Nova spots new construction and surface change in Karrada from
satellite imagery. It's written for a non-technical reader. No prior knowledge of
remote sensing is assumed.

## The short version

Nova compares the same patch of ground at two points in time and flags places that
went from "not built" to "built." It does this with simple, transparent math on the
colors each satellite pixel reflects, not with a black-box AI model. Every detection
can be traced back to a number you can check.

## The imagery

We use **Sentinel-2**, a free European satellite that photographs all of Iraq every
few days. Each pixel covers a **10 m × 10 m** square on the ground (about the size of
a small house plot). Sentinel-2 sees more than the human eye: alongside red, green,
and blue, it records **near-infrared** and **shortwave-infrared** light. Those extra
bands are what make change detection possible, because vegetation, bare soil, and
concrete each reflect them differently.

## The three "indices"

An index is just a ratio of two light bands that isolates one thing on the ground.
Each one returns a number roughly between -1 and +1.

- **NDVI — vegetation.** High when a pixel is green and growing (grass, trees, crops),
  low over concrete, roads, or bare dirt. Think of it as a "how alive is this pixel"
  score.
- **NDBI — built-up surface.** High over concrete, rooftops, and asphalt; low over
  vegetation. Think of it as a "how built-up is this pixel" score.
- **MNDWI — water.** High over open water. We use it only to find the Tigris so we can
  ignore it (see "Masking the river" below).

We compute all three for the "before" snapshot and the "after" snapshot, then look at
how each pixel *changed*.

## Why band math instead of a CV model

A computer-vision model that draws boxes around buildings sounds more impressive, but
at 10 m resolution it's the wrong tool:

- **A building is only a few pixels.** A typical Karrada house is 1–2 Sentinel-2
  pixels. There isn't enough detail for a model to recognize a "building" by shape.
- **No training data, no training cost.** A custom model would need thousands of
  hand-labeled Baghdad examples and GPU time we don't have before the demo. Band math
  needs neither.
- **It's explainable.** Every detection comes with the exact numbers that triggered it.
  We can show a client *why* a spot was flagged. A neural net can't do that as cleanly.
- **It's robust.** The same code runs over any AOI in Iraq with no retraining.

The trade-off: we detect *that* the ground changed, not *what kind* of building went up.
For the change-monitoring job Nova does, that's the right scope.

## The two time windows

We don't compare two single days, because any single image can be hazy, cloudy, or
shadowed. Instead we build a clean **median composite** of a whole summer — for each
pixel we take the median value across every clear image in the window, which removes
clouds and one-off noise.

- **Before:** 1 June 2022 → 1 September 2022
- **After:** 1 June 2024 → 1 September 2024

Both windows are the same season (summer), two years apart. Matching the season matters:
it keeps the sun angle and vegetation cycle comparable, so the changes we see are real
ground change rather than "it's spring vs. autumn."

## Masking the river

Karrada is a peninsula wrapped on three sides by the Tigris. River water shifts color
between years as its level and sediment change, and that can look like a "change" to the
math. Before flagging anything, Nova uses MNDWI to find water pixels and **removes them
from consideration**. In our run this excluded about 13% of the area and roughly 877
pixels that would otherwise have been false alarms over the river.

## What counts as a detection

A pixel is flagged as construction when **both** of these are true between the before and
after composites:

1. **Vegetation dropped** — NDVI fell by at least 0.10. Green or open ground went away.
2. **Built-up surface rose** — NDBI rose by at least 0.10. Concrete or rooftop appeared.

Requiring both at once is the key idea: lots of things change one index, but "green/bare
turning into concrete" is the specific fingerprint of new construction.

Neighboring flagged pixels are then grouped into a single polygon (one site), and we keep
a polygon only if it covers at least **1,000 m²**.

### Why ΔNDBI ≥ 0.10 and min area ≥ 1,000 m²

These two thresholds control how strict Nova is. We tuned them by running the pipeline at
several settings and checking the results against the map:

- A loose setting (NDBI rise ≥ 0.05, area ≥ 300 m²) produced **304** detections spread
  evenly across the whole peninsula. That's not believable — Karrada is already fully
  built, so genuine two-year construction should appear in a handful of redevelopment
  pockets, not everywhere at once. The even spread was mostly seasonal vegetation noise.
- The stricter setting we adopted (**NDBI rise ≥ 0.10, area ≥ 1,000 m²**) produced **50**
  detections that **cluster** in a few interior zones, away from the river edge. We
  measured this: the strongest detections sit about 40% closer together than random
  scatter would predict. That clustering is the signature of real development.

So the thresholds aren't arbitrary. They're the point where the output stops looking like
noise and starts looking like construction you could drive to.

## Two kinds of detection

After finding a changed site, Nova checks it against **Microsoft's Building Footprints** —
a free global dataset of building outlines traced from imagery. The label depends on
whether a footprint sits on the changed spot:

- **confirmed_change** — the change overlaps a known building footprint, so the change is
  corroborated by independent building data and a building exists at the site. Note Nova does
  *not* claim a brand-new vertical building — only that the change is confirmed by a footprint.
  (20 of our 50.)
- **candidate_change** — the change has no building on it. This is bare-ground change that may
  or may not be construction: graded land, a new road, a parking lot, or a site mid-construction.
  (30 of our 50.)

One honest caveat: the footprint dataset is a **single snapshot** with no "before" version,
so it confirms a building *exists today* but can't prove it's brand new on its own. The
proof that something *changed* comes entirely from the before/after satellite math. The
footprint just tells us whether that change is a building or open ground.

## Confidence score

Each detection gets a 0–1 confidence score that blends four signals: how strongly the
built-up index rose (40%), how large the site is (30%), whether a building footprint
confirms it (20%), and how much vegetation was lost (10%). Higher means more reliable.
The map can use this to show the strongest detections first.

## What this is not

- Not a building-type classifier. We don't claim "this is a hospital" — 10 m imagery
  can't support that.
- Not real-time. Each run compares two fixed time windows.
- Not a substitute for ground truth. It's a high-quality lead generator: it tells an
  analyst exactly where to look.
