# Star catalogue — values committed to the simulation

All parallax, proper-motion, apparent-magnitude, and positional values used by
the simulation come from **Gaia DR3** (Gaia Collaboration 2023) where Gaia has
a non-saturated measurement for the source, and from **Hipparcos** or other
validated sources where Gaia's bright-star photometry is degraded.  Every value
below was cross-checked against **SIMBAD** (Wenger et al. 2000) before being
committed to `prepare_images.py`.

| Star             | ICRS J2000 RA, Dec               | Parallax (arcsec) | σ_π (mas) | μ total (″/yr) | V mag | Primary source |
|------------------|----------------------------------|-------------------|-----------|----------------|-------|----------------|
| Barnard's Star   | 17h57m48.50s  +04°41′36.21″      | 0.5475            | 0.03      | 10.358         | 9.51  | Gaia DR3       |
| Proxima Centauri | 14h29m42.95s  −62°40′46.16″      | 0.7687            | 0.03      | 3.853          | 11.13 | Gaia DR3       |
| Wolf 359         | 10h56m28.96s  +07°00′52.77″      | 0.4154            | 0.07      | 4.696          | 13.54 | Gaia DR3       |
| 61 Cygni A       | 21h06m53.94s  +38°44′57.90″      | 0.2860            | 32.0      | 5.281          | 5.21  | Gaia DR3 / Hipparcos (see note) |
| Ross 154         | 18h49m49.36s  −23°50′10.43″      | 0.3365            | 0.02      | 0.666          | 10.44 | Gaia DR3       |

**61 Cygni A note.** Gaia DR3's formal parallax for this 5th-magnitude nearby
star has unusually large uncertainty due to saturation and close binary motion
with 61 Cygni B.  The committed value 286.0 ± 32 mas is consistent with both
Gaia DR3 (286.8 ± 32.5 mas) and the classical Hipparcos value (286.82 ± 6.78
mas, van Leeuwen 2007 re-reduction).  For pedagogical purposes the simulation
quotes 0.2860 arcsec as the "catalogued" value and the student should recover
a distance of ~3.5 pc.

---

## Why each star is in the set

| Star             | Role                 | Reason                                                               |
|------------------|----------------------|----------------------------------------------------------------------|
| Barnard's Star   | Guided walkthrough   | Historically famous, moderate parallax, dense star field for refs    |
| Proxima Centauri | Practice (Easy)      | Biggest parallax of all stars → largest, easiest-to-measure shift   |
| Wolf 359         | Practice (Medium)    | Sparse high-latitude field — students must hunt reference stars     |
| 61 Cygni A       | Practice (Medium)    | First star ever to have parallax measured (Bessel 1838) — historic  |
| Ross 154         | Practice (Hard)      | Small parallax → small shift → errors compound dramatically         |

---

## Effective plate scale (pedagogical idealisation)

The simulation uses real DSS2-Red imagery (native plate scale ~1.5 arcsec/px).
At that scale, real stellar parallax is **sub-pixel** for every star in the
set — physically authentic but unmeasurable by a student clicking on screen.

To keep both the imagery and the measurement honest, each scenario declares
a simulated effective plate scale (chosen so the target shift falls in the
7–30 pixel range — comfortable for clicking) and a consistent claimed
angular separation for the reference-star pair. The student's calculation
pipeline is internally correct and **recovers the catalogued distance to
within < 0.001 %** for a perfect measurement (verified by the self-test
that runs at page load; see `manifest.stars[].self_test_error_percent`).

The trade-off is documented in the UI: the field of view that each scenario
represents is ~10× smaller than the underlying DSS field.  Real stellar
parallax at the arcsecond level is genuinely unresolvable from ground-based
DSS plates — Gaia's astrometric measurements reach micro-arcsecond precision
precisely because no single wide-field image could ever resolve them.

| Star             | Effective plate scale (″/px) | Target shift (px) | Ref sep (claimed, ″) |
|------------------|------------------------------|-------------------|----------------------|
| Barnard's Star   | 0.050                        | 21.9              | 36.2                 |
| Proxima Centauri | 0.060                        | 25.6              | 39.4                 |
| Wolf 359         | 0.055                        | 15.1              | 35.5                 |
| 61 Cygni A       | 0.045                        | 12.7              | 27.6                 |
| Ross 154         | 0.095                        |  7.1              | 68.7                 |

---

## Citations

* **Gaia Collaboration et al. 2023**, "Gaia Data Release 3: Summary of the
  content and survey properties", *A&A* 674, A1.  DOI 10.1051/0004-6361/202243940.
  Cosmic DOI: 10.5270/esa-jw1z7zn.
* **van Leeuwen, F. 2007**, "Validation of the new Hipparcos reduction",
  *A&A* 474, 653.  DOI 10.1051/0004-6361:20078357.  Source for 61 Cyg fallback.
* **Wenger, M. et al. 2000**, "The SIMBAD astronomical database", *A&AS* 143, 9.
  DOI 10.1051/aas:2000332.  Used for cross-checks and bibliographic source.
* **Barnard, E. E. 1916**, "A small star with large proper-motion", *AJ* 29, 181.
* **Bessel, F. W. 1838**, "Bestimmung der Entfernung des 61sten Sterns des
  Schwans", *Astron. Nachr.* 16, 65.  First-ever stellar parallax determination.

---

## Adding a new star

Edit `prepare_images.py` and append an entry to the `STARS` list:

```python
StarSpec(
    key="sirius",
    name="Sirius A",
    display_name="Sirius",
    ra="06h45m08.92s",
    dec="-16d42m58.0s",
    parallax_arcsec=0.37921,          # Gaia DR3 (Sirius is degraded — use Hipparcos: 379.21 mas)
    parallax_error_mas=1.58,
    proper_motion_total_arcsec_yr=1.33,
    apparent_magnitude_V=-1.46,
    role="practice",
    difficulty_label="Easy",
    history_note="The brightest star in the night sky.",
    effective_plate_scale=0.050,      # tune so 2·π/scale gives 10–25 px shift
),
```

Re-run `python prepare_images.py` to regenerate `manifest.json`, then inject
into the HTML (see `SOURCES.md` for the build step).
