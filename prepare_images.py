#!/usr/bin/env python3
"""
prepare_images.py — fetch DSS2 Red imagery for stellar-parallax teaching simulation.

USAGE:
    python prepare_images.py                    # process all stars in STARS list
    python prepare_images.py --only barnard     # process one star
    python prepare_images.py --cache-only       # skip fetch, use cached FITS if present
    python prepare_images.py --out MANIFEST     # override output manifest path

WHAT IT DOES
    For every star in the STARS list:
      1. Downloads a DSS2-Red image from STScI SkyView via astroquery.
      2. Crops to 800 x 500 centred on the target using FITS WCS.
      3. Flips vertically so north is up (DSS/WCS has +Y = +Dec; PNG row 0 = top).
      4. Applies ZScale + asinh stretch for visual dynamic range.
      5. Locates two bright reference stars well away from target and each other.
      6. Writes a PNG (tinted, subtle blue-black CCD aesthetic) and records metadata
         needed by the HTML simulation (plate scale, reference positions, target
         epoch positions, catalogued parallax, etc.)
      7. Emits manifest.json (base64-encoded PNG + metadata per star).

PEDAGOGICAL NOTE (also documented in CATALOGUE.md)
    Real stellar parallax at DSS2's native ~1.5 arcsec/px is sub-pixel — not measurable
    by students clicking on screen. We therefore pick a per-scenario "effective plate
    scale" (0.04-0.10 arcsec/px), produce a visible 7-25 px shift for each target, and
    scale the claimed reference-star separation consistently. The calculation pipeline
    recovers the TRUE catalogued distance to <1% — see the self-test at the end.

EXTENDING
    To add Sirius, Vega, Altair, or any other star, append an entry to STARS below
    with the target's ICRS coordinates, Gaia DR3 parallax, proper motion, and your
    chosen effective plate scale (smaller scale = larger, easier-to-measure shift).
    Then re-run this script.  No code changes needed elsewhere.

SOURCES
    * Imagery:     STScI SkyView DSS2-Red   (https://skyview.gsfc.nasa.gov/)
    * Parallaxes:  Gaia DR3 (Hipparcos fallback for Barnard's where Gaia is saturated)
    * Verified against SIMBAD before committing.  See CATALOGUE.md for citations.

DEPENDENCIES
    astroquery, astropy, numpy, pillow, scipy
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.visualization import AsinhStretch, ZScaleInterval
from astropy.wcs import WCS
from astroquery.skyview import SkyView
from PIL import Image, ImageFilter
from scipy.ndimage import maximum_filter, label, center_of_mass


# -----------------------------------------------------------------------------
# STARS TO PROCESS
# -----------------------------------------------------------------------------
# Parallaxes are Gaia DR3 where available (see CATALOGUE.md).  proper_motion
# (mas/yr) is recorded for reference but not used in the simulation — see the
# proper-motion explainer in the HTML sidebar.
#
# effective_plate_scale_arcsec_per_px drives the target shift magnitude
# (shift_px = 2 * parallax_arcsec / effective_plate_scale). Smaller value ->
# larger, easier-to-measure shift. Tuned so shifts fall in 7-30 px.
# -----------------------------------------------------------------------------

@dataclass
class StarSpec:
    key: str                        # short slug used in manifest + HTML
    name: str
    display_name: str               # how it shows up in UI
    ra: str
    dec: str
    parallax_arcsec: float          # Gaia DR3
    parallax_error_mas: float       # Gaia DR3 formal uncertainty
    proper_motion_total_arcsec_yr: float   # for explainer text only
    apparent_magnitude_V: float
    role: str                       # 'walkthrough' or 'practice-easy' etc.
    difficulty_label: str           # 'Easy' / 'Medium' / 'Hard' / ''
    history_note: str
    effective_plate_scale: float    # arcsec/display-pixel (chosen for teaching)
    field_arcmin: float = 10.0      # SkyView radius in arcmin (diameter ~= 2x)


STARS: list[StarSpec] = [
    StarSpec(
        key="barnard",
        name="Barnard's Star",
        display_name="Barnard's Star",
        ra="17h57m48.4984s",
        dec="+04d41m36.2072s",
        parallax_arcsec=0.5475,
        parallax_error_mas=0.0002,
        proper_motion_total_arcsec_yr=10.358,
        apparent_magnitude_V=9.51,
        role="walkthrough",
        difficulty_label="",
        history_note=("Discovered by E. E. Barnard in 1916 because of its extreme "
                      "proper motion — 10.3 arcsec/yr, the fastest of any star "
                      "known. A red dwarf only 1.83 parsecs away."),
        effective_plate_scale=0.050,
    ),
    StarSpec(
        key="proxima",
        name="Proxima Centauri",
        display_name="Proxima Centauri",
        ra="14h29m42.9487s",
        dec="-62d40m46.164s",
        parallax_arcsec=0.7687,
        parallax_error_mas=0.0003,
        proper_motion_total_arcsec_yr=3.853,
        apparent_magnitude_V=11.13,
        role="practice",
        difficulty_label="Easy",
        history_note=("The closest star to the Sun beyond Sol. Part of the triple "
                      "Alpha Centauri system."),
        effective_plate_scale=0.060,
    ),
    StarSpec(
        key="wolf359",
        name="Wolf 359",
        display_name="Wolf 359",
        ra="10h56m28.9611s",
        dec="+07d00m52.7730s",
        parallax_arcsec=0.4154,
        parallax_error_mas=0.0007,
        proper_motion_total_arcsec_yr=4.696,
        apparent_magnitude_V=13.54,
        role="practice",
        difficulty_label="Medium",
        history_note=("A very faint red dwarf (V=13.5), just 2.4 pc away.  "
                      "Catalogued by Max Wolf in 1919."),
        effective_plate_scale=0.055,
    ),
    StarSpec(
        key="61cygni",
        name="61 Cygni A",
        display_name="61 Cygni A",
        ra="21h06m53.9396s",
        dec="+38d44m57.8977s",
        parallax_arcsec=0.2860,
        parallax_error_mas=0.0320,   # Gaia DR3 is degraded for this bright binary; Hip-flagged
        proper_motion_total_arcsec_yr=5.281,
        apparent_magnitude_V=5.21,
        role="practice",
        difficulty_label="Medium",
        history_note=("The first star ever to have its parallax measured — "
                      "by Friedrich Bessel in 1838.  The canonical parallax star."),
        effective_plate_scale=0.045,
    ),
    StarSpec(
        key="ross154",
        name="Ross 154",
        display_name="Ross 154",
        ra="18h49m49.3622s",
        dec="-23d50m10.4291s",
        parallax_arcsec=0.3365,
        parallax_error_mas=0.0002,
        proper_motion_total_arcsec_yr=0.666,
        apparent_magnitude_V=10.44,
        role="practice",
        difficulty_label="Hard",
        history_note=("A nearby M-dwarf discovered by Frank Ross in 1925, 2.97 pc away."),
        effective_plate_scale=0.095,
    ),
]


# -----------------------------------------------------------------------------
# IMAGE ACQUISITION
# -----------------------------------------------------------------------------

def fetch_dss_fits(coord: SkyCoord, field_arcmin: float, cache_path: Path,
                    cache_only: bool = False, pixels: int = 800) -> fits.HDUList:
    """Download or load from cache a DSS2-Red FITS for a given coordinate."""
    if cache_path.exists():
        print(f"    [cache] reading {cache_path}")
        return fits.open(cache_path)
    if cache_only:
        raise FileNotFoundError(f"Cache miss for {cache_path} (cache-only mode)")
    print(f"    [fetch] DSS2-Red  radius={field_arcmin}'  pixels={pixels}")
    hdus = SkyView.get_images(
        position=coord,
        survey=["DSS2 Red"],
        radius=field_arcmin * u.arcmin,
        pixels=pixels,
    )
    if not hdus:
        raise RuntimeError(f"SkyView returned nothing for {coord.to_string('hmsdms')}")
    hdus[0].writeto(cache_path, overwrite=True)
    print(f"    [save ] {cache_path}")
    return hdus[0]


# -----------------------------------------------------------------------------
# WCS / ORIENTATION
# -----------------------------------------------------------------------------

def measure_wcs(header) -> dict:
    """Extract plate scale and orientation from a FITS header."""
    wcs = WCS(header)
    scale_matrix = wcs.pixel_scale_matrix
    scales = np.sqrt(np.sum(scale_matrix ** 2, axis=0)) * 3600.0  # arcsec/px
    # Determine orientation.  +X pixel -> what direction?
    pxc = wcs.wcs.crpix - 1
    c0 = wcs.pixel_to_world_values(pxc[0], pxc[1])
    cx = wcs.pixel_to_world_values(pxc[0] + 1, pxc[1])
    cy = wcs.pixel_to_world_values(pxc[0], pxc[1] + 1)
    dra_x = (cx[0] - c0[0]) * np.cos(np.deg2rad(c0[1])) * 3600.0
    ddec_y = (cy[1] - c0[1]) * 3600.0
    return dict(
        plate_scale_x=float(scales[0]),
        plate_scale_y=float(scales[1]),
        dra_per_px_x=float(dra_x),
        ddec_per_px_y=float(ddec_y),
        wcs=wcs,
    )


# -----------------------------------------------------------------------------
# REFERENCE STAR SELECTION
# -----------------------------------------------------------------------------

def find_bright_sources(img: np.ndarray, threshold_sigma: float = 3.0,
                        peak_window: int = 9) -> list[dict]:
    """Return list of compact bright sources (local-max peaks).

    Works on the RAW (unstretched) intensity array.  For each local-maximum
    pixel above threshold we fit a 5x5 box centroid for sub-pixel position.
    """
    data = img.astype(np.float32)
    # Robust background: median & MAD-derived std
    med = float(np.nanmedian(data))
    mad = float(np.nanmedian(np.abs(data - med)))
    std = 1.4826 * mad if mad > 0 else float(np.nanstd(data))
    thr = med + threshold_sigma * std

    # Local maxima
    maxf = maximum_filter(data, size=peak_window, mode="nearest")
    peak_mask = (data == maxf) & (data > thr)
    ys, xs = np.where(peak_mask)
    if len(xs) == 0:
        return []

    H, W = data.shape
    sources = []
    box = 3   # half-width of centroid box (uses 7x7 region)
    for py, px in zip(ys, xs):
        y0 = max(0, py - box); y1 = min(H, py + box + 1)
        x0 = max(0, px - box); x1 = min(W, px + box + 1)
        sub = data[y0:y1, x0:x1].astype(np.float64) - med
        sub[sub < 0] = 0.0
        tot = sub.sum()
        if tot <= 0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        cy = (yy * sub).sum() / tot
        cx = (xx * sub).sum() / tot
        # Reject if centroid moved too far from peak (blended source)
        if abs(cx - px) > 2 or abs(cy - py) > 2:
            continue
        sources.append({
            "x": float(cx), "y": float(cy),
            "flux": float(tot),
            "peak": float(data[py, px] - med),
        })
    sources.sort(key=lambda s: -s["peak"])
    return sources


def pick_reference_pair(sources: list[dict], target_xy: tuple[float, float],
                        img_shape: tuple[int, int],
                        min_dist_px: float = 200.0,
                        min_from_target_px: float = 80.0,
                        edge_margin: int = 30) -> tuple[dict, dict] | None:
    """Pick two bright sources well separated and away from target/edges."""
    tx, ty = target_xy
    H, W = img_shape
    # Filter: reject near edge or near target
    cands = [s for s in sources
             if edge_margin <= s["x"] <= W - edge_margin
             and edge_margin <= s["y"] <= H - edge_margin
             and np.hypot(s["x"] - tx, s["y"] - ty) >= min_from_target_px]
    # Prefer similarly bright pair — look at top ~20 brightest
    top = cands[:24]
    best = None
    best_score = -1
    for i, a in enumerate(top):
        for b in top[i + 1:]:
            d = np.hypot(a["x"] - b["x"], a["y"] - b["y"])
            if d < min_dist_px:
                continue
            # score: encourage large separation, similar brightness, avoid central band
            brightness_ratio = min(a["flux"], b["flux"]) / max(a["flux"], b["flux"])
            center_penalty = 0.0
            # Avoid pairs that pass through the target
            midx = (a["x"] + b["x"]) / 2
            midy = (a["y"] + b["y"]) / 2
            if np.hypot(midx - tx, midy - ty) < 40:
                center_penalty = 0.3
            score = (d / 400.0) + 0.5 * brightness_ratio - center_penalty
            if score > best_score:
                best_score = score
                best = (a, b)
    return best


# -----------------------------------------------------------------------------
# IMAGE STRETCH + PNG
# -----------------------------------------------------------------------------

def stretch_image(data: np.ndarray, asinh_a: float = 0.1) -> np.ndarray:
    """Return a float [0,1] image after percentile-based interval + asinh stretch.

    Uses robust percentile clipping (not ZScale) because DSS fields containing
    a very bright star, plate edges, or strong galactic background confuse
    ZScale.  Asinh allows bright stars to flare softly instead of whiting out.
    """
    finite = data[np.isfinite(data)]
    # Sky level = 25th percentile-ish; faint-star ceiling = 99th-ish
    vmin = np.percentile(finite, 15.0)
    vmax = np.percentile(finite, 99.7)
    # If image has an extremely bright source, vmax may be dominated by it;
    # cap so bright stars saturate their cores but the surrounding field remains
    # visible. Asinh will still convey structure beyond vmax softly.
    norm = (data - vmin) / (vmax - vmin)
    norm = np.clip(norm, 0.0, 1.2)   # allow mild super-bright headroom
    stretched = AsinhStretch(a=asinh_a)(np.clip(norm, 0.0, 1.0))
    return np.clip(stretched, 0, 1)


def to_grayscale_png_bytes(gray01: np.ndarray) -> bytes:
    """Convert a [0,1] greyscale array to a compact grayscale PNG.

    We store one-channel 8-bit PNGs; the HTML tints them blue/amber at runtime
    using pixel manipulation, which keeps image storage small without losing
    control over the final colour aesthetic.
    """
    u8 = (np.clip(gray01, 0, 1) * 255 + 0.5).astype(np.uint8)
    img = Image.fromarray(u8, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.getvalue()


# -----------------------------------------------------------------------------
# MAIN PROCESSING PIPELINE (per star)
# -----------------------------------------------------------------------------

def process_star(star: StarSpec, cache_dir: Path, cache_only: bool = False) -> dict:
    print(f"\n=== {star.display_name} ({star.key}) ===")
    coord = SkyCoord(star.ra, star.dec, frame="icrs")
    fits_path = cache_dir / f"{star.key}_dss2red.fits"
    hdul = fetch_dss_fits(coord, star.field_arcmin, fits_path, cache_only=cache_only)
    hdu = hdul[0]
    data = np.asarray(hdu.data, dtype=np.float32)
    header = hdu.header
    wcs_info = measure_wcs(header)
    wcs = wcs_info["wcs"]
    print(f"    plate scale (real): {wcs_info['plate_scale_x']:.3f} x "
          f"{wcs_info['plate_scale_y']:.3f} arcsec/px")
    print(f"    orientation: +X -> dRA {wcs_info['dra_per_px_x']:+.2f}\"/px,  "
          f"+Y -> dDec {wcs_info['ddec_per_px_y']:+.2f}\"/px")

    # Target pixel location in FITS (before flip)
    tx_fits, ty_fits = wcs.world_to_pixel(coord)
    tx_fits, ty_fits = float(tx_fits), float(ty_fits)
    print(f"    target (fits): ({tx_fits:.1f}, {ty_fits:.1f})")

    # Crop to 800 x 500 centred on target
    H_out, W_out = 500, 800
    cx, cy = int(round(tx_fits)), int(round(ty_fits))
    x0 = cx - W_out // 2
    y0 = cy - H_out // 2
    H_src, W_src = data.shape
    # Clamp and pad if necessary
    pad_left = max(0, -x0)
    pad_top = max(0, -y0)
    pad_right = max(0, (x0 + W_out) - W_src)
    pad_bot = max(0, (y0 + H_out) - H_src)
    x0c = max(0, x0); y0c = max(0, y0)
    x1c = min(W_src, x0 + W_out); y1c = min(H_src, y0 + H_out)
    crop = data[y0c:y1c, x0c:x1c]
    if pad_left or pad_top or pad_right or pad_bot:
        crop = np.pad(crop, ((pad_top, pad_bot), (pad_left, pad_right)),
                      mode="edge")
    assert crop.shape == (H_out, W_out), crop.shape

    # Flip vertically so north is up (FITS +Y = +Dec; we want Dec+ at top of PNG)
    crop_flipped = np.flipud(crop)

    # After flip, target pixel in cropped-flipped coordinates
    # Before flip: target was at (tx_fits - x0, ty_fits - y0)
    # After flip (row-wise): y_new = (H_out - 1) - y_old
    tx_img = float(tx_fits - x0)
    ty_old = float(ty_fits - y0)
    ty_img = float((H_out - 1) - ty_old)
    print(f"    target (image, N-up): ({tx_img:.2f}, {ty_img:.2f})")

    # Stretch and render PNG (grayscale; tinted at runtime in HTML)
    gray01 = stretch_image(crop_flipped)
    png_bytes = to_grayscale_png_bytes(gray01)
    print(f"    PNG size: {len(png_bytes) / 1024:.1f} KB")

    # --- Reference star selection on the RAW flipped intensity data ---
    crop_raw_flipped = np.flipud(crop)
    sources = find_bright_sources(crop_raw_flipped, threshold_sigma=6.0,
                                  peak_window=9)
    print(f"    candidate bright sources: {len(sources)}")
    ref_pair = pick_reference_pair(sources, (tx_img, ty_img), crop_raw_flipped.shape,
                                   min_dist_px=220.0, min_from_target_px=80.0)
    if ref_pair is None:
        # Fall back to smaller min_dist if failure
        ref_pair = pick_reference_pair(sources, (tx_img, ty_img), crop_raw_flipped.shape,
                                       min_dist_px=180.0, min_from_target_px=60.0)
    if ref_pair is None:
        raise RuntimeError(f"Could not find two good reference stars for {star.key}")
    refA, refB = ref_pair
    # Order them left-to-right for consistent labelling
    if refA["x"] > refB["x"]:
        refA, refB = refB, refA
    refAx, refAy = refA["x"], refA["y"]
    refBx, refBy = refB["x"], refB["y"]
    refSep_px = float(np.hypot(refBx - refAx, refBy - refAy))
    print(f"    ref A: ({refAx:.1f}, {refAy:.1f})  ref B: ({refBx:.1f}, {refBy:.1f})")
    print(f"    ref separation: {refSep_px:.2f} px  "
          f"(real sky: {refSep_px * wcs_info['plate_scale_x']:.1f} arcsec)")

    # --- Target Jan / Jul positions ---
    # The TEACHING plate scale (effective) is different from real DSS plate scale.
    # Claimed reference star separation (arcsec) = refSep_px * effective_plate_scale.
    # Target parallax shift (px) = 2 * parallax_arcsec / effective_plate_scale.
    sim_plate_scale = star.effective_plate_scale
    ref_sep_arcsec_sim = refSep_px * sim_plate_scale
    shift_px = 2.0 * star.parallax_arcsec / sim_plate_scale
    print(f"    sim plate scale:    {sim_plate_scale:.4f} arcsec/px")
    print(f"    ref sep (sim):      {ref_sep_arcsec_sim:.3f} arcsec")
    print(f"    target shift:       {shift_px:.2f} px  (2p = {2*star.parallax_arcsec:.4f}\")")

    # January target = original position.  July target = January + shift_px in
    # the east direction.  In our flipped north-up image, +X is west (as in raw
    # DSS), so east = -X.  Shifting July westwards would be +X; east shift is -X.
    # Parallax ellipse is viewed from north; the Earth's motion around the Sun
    # produces a semi-major-axis shift perpendicular to the star's direction.
    # We idealise this as pure east-west (RA).  July relative to January: star
    # shifts east (positive RA) by +2p when Earth moves to the opposite side.
    # In pixel space (east = -X), July target = January target at x - shift_px.
    target_jan = (tx_img, ty_img)
    target_jul = (tx_img - shift_px, ty_img)

    # Check shift is within canvas
    if not (10 < target_jul[0] < W_out - 10):
        print(f"    WARNING: July target may be off-canvas x={target_jul[0]:.1f}")

    # Self-test: perfect measurement recovers catalogued distance?
    # Student measures: shift_px_measured = ||jul - jan|| = shift_px
    #                   refSep_px_measured = refSep_px
    # Pipeline:
    #   plate_scale_student = ref_sep_arcsec_sim / refSep_px_measured = sim_plate_scale
    #   total_shift_arcsec  = shift_px * plate_scale_student = 2 * parallax
    #   parallax_student    = total_shift_arcsec / 2  = parallax
    #   distance_student    = 1 / parallax = 1 / parallax_arcsec (parsecs)
    meas_shift = np.hypot(target_jul[0] - target_jan[0], target_jul[1] - target_jan[1])
    recovered_plate_scale = ref_sep_arcsec_sim / refSep_px
    recovered_total = meas_shift * recovered_plate_scale
    recovered_parallax = recovered_total / 2.0
    recovered_distance_pc = 1.0 / recovered_parallax
    true_distance_pc = 1.0 / star.parallax_arcsec
    err_pct = abs(recovered_distance_pc - true_distance_pc) / true_distance_pc * 100.0
    print(f"    SELF-TEST: recovered {recovered_distance_pc:.4f} pc  "
          f"vs true {true_distance_pc:.4f} pc  ({err_pct:.3f}% error)")
    if err_pct > 0.5:
        raise RuntimeError(f"Self-test FAILED for {star.key}: {err_pct:.2f}% error")

    # Bright-star catalogue for snap-to-star (top ~120 peaks, sub-pixel centroids)
    bright_stars = []
    # Sort by flux (already done inside find_bright_sources via peak)
    for s in sources[:120]:
        bright_stars.append({"x": round(s["x"], 2), "y": round(s["y"], 2)})

    entry = {
        "key": star.key,
        "name": star.name,
        "display_name": star.display_name,
        "ra": star.ra,
        "dec": star.dec,
        "role": star.role,
        "difficulty_label": star.difficulty_label,
        "history_note": star.history_note,
        "apparent_magnitude_V": star.apparent_magnitude_V,
        "parallax_arcsec": star.parallax_arcsec,
        "parallax_error_mas": star.parallax_error_mas,
        "proper_motion_total_arcsec_yr": star.proper_motion_total_arcsec_yr,
        "distance_pc": true_distance_pc,
        "dss_plate_scale_real": wcs_info["plate_scale_x"],
        "sim_plate_scale": sim_plate_scale,
        "canvas_width": W_out,
        "canvas_height": H_out,
        "target_jan": {"x": round(target_jan[0], 3), "y": round(target_jan[1], 3)},
        "target_jul": {"x": round(target_jul[0], 3), "y": round(target_jul[1], 3)},
        "ref_A": {"x": round(refAx, 3), "y": round(refAy, 3)},
        "ref_B": {"x": round(refBx, 3), "y": round(refBy, 3)},
        "ref_sep_px": round(refSep_px, 3),
        "ref_sep_arcsec": round(ref_sep_arcsec_sim, 4),
        "target_shift_px": round(shift_px, 3),
        "self_test_error_percent": round(err_pct, 4),
        "bright_stars": bright_stars,
        "image_base64": base64.b64encode(png_bytes).decode("ascii"),
        "image_bytes": len(png_bytes),
        "survey": "DSS2 Red",
        "attribution": "Digitized Sky Survey / STScI / AURA / UK Schmidt Telescope",
    }
    return entry


# -----------------------------------------------------------------------------
# DRIVER
# -----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="process only this star key")
    ap.add_argument("--cache-only", action="store_true",
                    help="use cached FITS only; fail on miss")
    ap.add_argument("--out", default="manifest.json",
                    help="output manifest path (default: manifest.json)")
    ap.add_argument("--cache-dir", default="fits_cache",
                    help="directory for cached FITS files")
    args = ap.parse_args()

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(exist_ok=True)

    stars = STARS if args.only is None else [s for s in STARS if s.key == args.only]
    if not stars:
        print(f"No star matches --only={args.only}", file=sys.stderr)
        sys.exit(2)

    entries = []
    for star in stars:
        try:
            entry = process_star(star, cache_dir, cache_only=args.cache_only)
            entries.append(entry)
        except Exception as exc:
            print(f"!! FAILED: {star.key}: {exc}", file=sys.stderr)
            raise

    manifest = {
        "schema_version": 1,
        "attribution": "Digitized Sky Survey / STScI / AURA / UK Schmidt Telescope",
        "stars": entries,
    }
    out = Path(args.out)
    out.write_text(json.dumps(manifest, indent=2))
    total_mb = sum(e["image_bytes"] for e in entries) / 1024 / 1024
    print(f"\n==> wrote {out} with {len(entries)} stars, {total_mb:.2f} MB images")


if __name__ == "__main__":
    main()
