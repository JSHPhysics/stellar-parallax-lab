# Image sources and transformations

All imagery in this simulation comes from the **Digitized Sky Survey (DSS2-Red)**,
fetched via the **STScI SkyView Virtual Observatory**.  The first-generation DSS
imagery was produced from photographic plates taken with the UK Schmidt Telescope
(southern survey) and Palomar Oschin Schmidt Telescope (northern survey), then
digitized at STScI.

Required attribution (included in the UI and in `manifest.json`):
**"Digitized Sky Survey / STScI / AURA / UK Schmidt Telescope"**

## Per-star image provenance

For every star the pipeline makes one SkyView request:

```
survey  = DSS2 Red
position = ICRS J2000 RA, Dec (see CATALOGUE.md)
radius   = 10 arcmin          (i.e. 20 arcmin field)
pixels   = 800
```

The returned FITS has:

* `CTYPE = RA---TAN, DEC--TAN` (tangent-plane gnomonic projection)
* `CDELT = ±0.000833°/px` → plate scale **1.500 arcsec/pixel** (confirmed from WCS)
* `CRVAL = requested RA, Dec`; `CRPIX = 400.5, 400.5` (centre)
* Orientation: `+X_px → −RA` (east-left standard), `+Y_px → +Dec`.  This is the
  usual FITS convention.  Because PNG row 0 is the top of the image, the raw
  array is displayed south-at-top; `prepare_images.py` applies `np.flipud`
  so the final PNG is **north-up, east-left**.

## Transformations applied (in order)

1. **WCS-centred crop** to 800 × 500 pixels around the target.
2. **Vertical flip** (`np.flipud`) for north-up orientation.
3. **Percentile clip** on the raw float32 intensity (15th–99.7th percentile).
4. **Asinh stretch** with `a = 0.1`, from `astropy.visualization.AsinhStretch`.
5. **Grayscale PNG encoding**, 8-bit, `optimize=True`, `compress_level=9`.
6. The HTML tints the grayscale PNG at runtime:
   * January epoch: cool blue tint (RGB ≈ 0.55, 0.78, 1.00 multiplier)
   * July epoch:    warm amber tint (RGB ≈ 1.00, 0.78, 0.50 multiplier)

No star has been artificially added, removed, or moved within the DSS imagery.
The target star remains visible at its real catalogued position in every frame.
The January/July target *markers* are synthetic overlays drawn on top of the
real image, positioned according to the simulation's effective plate scale
(see `CATALOGUE.md`).

## Reference-star detection

For each crop, `prepare_images.py` finds candidate bright sources using a
median + MAD background estimate followed by local-maximum peak detection and
sub-pixel centroiding on a 7×7 box.  It then chooses two bright stars that are:

* at least 220 pixels apart in the 800 × 500 crop
* at least 80 pixels from the target
* not adjacent to the image edge
* with a pair midpoint not passing through the target centre

Their catalogued angular separation (used for plate-scale calibration in the
simulation) is taken as **measured separation × effective plate scale**, which
keeps the student's calculation pipeline internally consistent.

## Licence and reuse

Per the [STScI DSS data release policy](https://archive.stsci.edu/dss/copyright.html),
DSS imagery is free for non-commercial, educational use provided the attribution
"Digitized Sky Survey / STScI / AURA" is included.  This attribution is shown
in the HTML footer and in the corner of every rendered image.

The UK Schmidt Telescope southern plates are jointly owned by the Royal
Observatory Edinburgh / Anglo-Australian Observatory.  Northern plates are from
the Palomar Oschin Schmidt Telescope (California Institute of Technology).

## Build steps (reproducing the manifest)

```bash
# From the project root
pip install astroquery astropy pillow numpy scipy
python prepare_images.py          # fetches FITS, writes manifest.json
python build_html.py              # injects manifest.json into parallax-lab.html
```

`prepare_images.py` caches FITS files in `./fits_cache/` so re-runs are
network-free.  Deleting the cache directory forces a fresh SkyView download.
