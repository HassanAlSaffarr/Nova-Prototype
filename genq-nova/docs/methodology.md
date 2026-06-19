# How Nova Detects Change

Nova's core job: spot **new construction and building changes** across Iraq from
satellite imagery — including projects with no online footprint — and put them on
a market-intelligence map. This explains how, written for a non-technical reader.

> **Status note.** Nova's detection method was rebuilt after the first prototype.
> This document describes the **current method (v2)**. The original approach (v1,
> vegetation/built-up indices) is documented at the end as *superseded*, with the
> evidence for why we moved on. Both are now selectable in the live demo (Nova
> detections → "High-res change" for v2, "v1 indices" for the superseded sets),
> on top of the existing-buildings base layer.

## The current method (v2): high-resolution structural change

**The key realization:** a building is only **1–4 pixels** in the free 10-metre
Sentinel-2 imagery the prototype used. At that size, a new building is
indistinguishable from bare soil or image noise. **No clever formula fixes that —
the problem is resolution.** So Nova v2 works on **~0.5-metre imagery**, where
buildings are obvious.

Nova v2 runs as a **tiered pipeline** — cheap-and-frequent to find *where* to
look, then sharp-and-targeted to confirm *what* changed:

1. **Trigger (free, frequent).** Sentinel-1/2 pass over every few days and flag
   coarse "something may have changed here" areas. High recall, low precision —
   that's fine; it's just an alarm that narrows where we spend effort.
2. **Confirm (high-resolution).** On flagged areas, Nova pulls **before/after
   half-metre imagery for two dates** from the free **Esri World Imagery Wayback**
   archive (≈190 dated versions back to 2014). New construction shows up as
   **structure appearing where there was smooth, bare land** — the local image
   "texture" jumps from a low baseline. That's the detection.
3. **Verify.** Each detection is cross-checked against the internet, permits, and
   the other GENQ agents. Note this is **one-directional**: finding online
   evidence confirms a project, but *absence* of evidence doesn't mean it's false
   — many Iraqi projects have no online record (which is exactly why Nova exists).

## Why this is the right signal

We didn't just assume — we tested it on ground truth. Comparing **Bismayah New
City** (a documented 100,000-unit project actively under construction) against
**central Karrada** (a built-out, saturated district):

| Method | Bismayah (building) | Karrada (saturated) | Tells them apart? |
|---|---|---|---|
| 10 m vegetation/built-up indices | noise | noise | No |
| 10 m radar backscatter | ~15/km² | ~15/km² | **No (1.0×)** |
| **v2 high-resolution structural change** | **31% flagged** | **5% flagged** | **Yes (~6×)** |

A valid detector must light up where construction is *known* to be happening and
stay quiet where it isn't. Only the high-resolution method does.

## What it is and isn't
- It finds **new structures appearing**, not vegetation change.
- The current version uses a transparent image-texture signal; the natural
  upgrade is a **deep-learning building-footprint model** for sharper, per-building
  output.
- It's a high-quality **lead generator**: it tells an analyst exactly where to
  look, and the other agents corroborate.

---

## Superseded: v1 (vegetation / built-up indices)

The first prototype detected change with **band math** on free 10 m Sentinel-2:
NDVI (vegetation), NDBI (built-up), MNDWI (water), differenced between two dates,
flagging pixels where vegetation fell and "built-up" rose.

**Why we moved off it — the evidence:**
- **NDBI confuses buildings with bare soil**, a documented failure that is
  *worst in dry climates*. Baghdad is arid and the Tigris exposes sand/mud banks,
  so the index fired on dried/cleared ground as if it were construction.
- On ground truth it had **no discriminating power**: 10 m radar fired equally on
  a known mega-project and saturated Karrada (1.0×). At 10 m, a building is too
  few pixels to separate from noise.
- **Vegetation change is the wrong primary signal** for construction — it only
  catches greenfield development and false-fires on seasonal drying.

v1 was a reasonable, fast way to stand up an end-to-end prototype. It was the
right thing to *start* with and the wrong thing to *ship*. The v2 method above is
what a production Nova is built on.
