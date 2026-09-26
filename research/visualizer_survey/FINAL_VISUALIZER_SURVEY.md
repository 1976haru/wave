# FINAL VISUALIZER SURVEY

## Scope

- GitHub projects searched and deeply reviewed: **60**
- README/source context checked: **56**
- Repository LICENSE files directly found: **40**
- License triage: GREEN 37 / YELLOW 2 / RED 21
- Production renderer changed: **NO**
- Version changed: **NO (0.8.3.9)**

> License labels are preliminary engineering triage, not legal advice. Re-check the exact version and dependencies before reuse.

## First shortlist - 25

1. **NickvisionApps/Cavalier** — dots, bars; MIT / GREEN; ref 50, beauty 58, Tokyo 60.
2. **wizgrav/clubber** — LED, dots, bars, waveform, shader, line; MIT / GREEN; ref 62, beauty 49, Tokyo 59.
3. **Bauxitedev/spectral-visualizer** — LED, dots, bars; NOASSERTION / RED; ref 70, beauty 48, Tokyo 59.
4. **katspaugh/wavesurfer.js** — bars, waveform, line; BSD-3-Clause / GREEN; ref 32, beauty 63, Tokyo 53.
5. **alex2wong/vudio** — LED, bars, waveform, line; NOASSERTION / RED; ref 54, beauty 66, Tokyo 59.
6. **foobar404/wave.js** — bars, line; MIT / GREEN; ref 32, beauty 59, Tokyo 51.
7. **marcopixel/monstercat-visualizer** — bars; MIT / GREEN; ref 32, beauty 59, Tokyo 51.
8. **staskobzar/vue-audio-visual** — bars, waveform, radial, line; MIT / GREEN; ref 40, beauty 59, Tokyo 49.
9. **deftio/WebAudioSpectrum** — bars, waveform, line; MIT / GREEN; ref 32, beauty 55, Tokyo 49.
10. **ranshufang55/sonascope** — bars, waveform, line; MIT / GREEN; ref 32, beauty 54, Tokyo 49.
11. **michaelbromley/soundcloud-visualizer** — LED, bars; MIT / GREEN; ref 44, beauty 49, Tokyo 48.
12. **clarkezone/audiovisualizer** — LED, bars, line; MIT / GREEN; ref 44, beauty 48, Tokyo 48.
13. **TheWisker/Cavasik** — LED, particles, bars, line; GPL-3.0 / RED; ref 44, beauty 66, Tokyo 58.
14. **zz-plant/stims** — LED, bars, waveform, shader, line, full-screen; Unlicense / GREEN; ref 54, beauty 64, Tokyo 55.
15. **phip1611/audio-visualizer** — LED, bars, waveform, line; MIT / GREEN; ref 44, beauty 47, Tokyo 47.
16. **wayou/HTML5_Audio_Visualizer** — bars; MIT / GREEN; ref 32, beauty 51, Tokyo 47.
17. **wayne-wu/webgl-music-visualizer** — bars, line; NOASSERTION / RED; ref 42, beauty 64, Tokyo 57.
18. **chrisweb/waveform-visualizer** — LED, waveform, line; MIT / GREEN; ref 42, beauty 55, Tokyo 47.
19. **macobo/WebGL-Audio-Visualization** — LED, particles, bars; MIT / GREEN; ref 44, beauty 56, Tokyo 54.
20. **scottlawsonbc/audio-reactive-led-strip** — LED; MIT / GREEN; ref 34, beauty 61, Tokyo 48.
21. **zogi/spectrum-analyzer-js** — bars; NOASSERTION / GREEN; ref 32, beauty 46, Tokyo 45.
22. **DevonCrawford/LED-Music-Visualizer** — LED, waveform; MIT / GREEN; ref 34, beauty 59, Tokyo 47.
23. **DodekaHydra/arcane.gl** — LED, bars, radial; BSD-2-Clause / GREEN; ref 44, beauty 55, Tokyo 49.
24. **jasonulbright/wavescope** — LED, particles, bars, waveform, shader, line, full-screen; MIT / GREEN; ref 52, beauty 59, Tokyo 53.
25. **margox/vudio.js** — waveform; NOASSERTION / RED; ref 32, beauty 68, Tokyo 52.

## Tokyo Chill visual shortlist - 15

1. **Bauxitedev/spectral-visualizer** — Ref 70, Beauty 48, Hip 51, Lower-third 68, Composition 65, License RED.
2. **wizgrav/clubber** — Ref 62, Beauty 49, Hip 57, Lower-third 68, Composition 57, License GREEN.
3. **alex2wong/vudio** — Ref 54, Beauty 66, Hip 62, Lower-third 56, Composition 59, License RED.
4. **NickvisionApps/Cavalier** — Ref 50, Beauty 58, Hip 65, Lower-third 68, Composition 60, License GREEN.
5. **jasonulbright/wavescope** — Ref 52, Beauty 59, Hip 66, Lower-third 38, Composition 59, License GREEN.
6. **TheWisker/Cavasik** — Ref 44, Beauty 66, Hip 68, Lower-third 56, Composition 59, License RED.
7. **zz-plant/stims** — Ref 54, Beauty 64, Hip 65, Lower-third 38, Composition 52, License GREEN.
8. **wayne-wu/webgl-music-visualizer** — Ref 42, Beauty 64, Hip 69, Lower-third 56, Composition 58, License RED.
9. **macobo/WebGL-Audio-Visualization** — Ref 44, Beauty 56, Hip 63, Lower-third 56, Composition 55, License GREEN.
10. **staskobzar/vue-audio-visual** — Ref 40, Beauty 59, Hip 59, Lower-third 41, Composition 60, License GREEN.
11. **chrisweb/waveform-visualizer** — Ref 42, Beauty 55, Hip 51, Lower-third 40, Composition 58, License GREEN.
12. **michaelbromley/soundcloud-visualizer** — Ref 44, Beauty 49, Hip 45, Lower-third 56, Composition 53, License GREEN.
13. **clarkezone/audiovisualizer** — Ref 44, Beauty 48, Hip 44, Lower-third 56, Composition 53, License GREEN.
14. **katspaugh/wavesurfer.js** — Ref 32, Beauty 63, Hip 63, Lower-third 56, Composition 58, License GREEN.
15. **phip1611/audio-visualizer** — Ref 44, Beauty 47, Hip 43, Lower-third 56, Composition 52, License GREEN.

## Prototype set - 12 distinct visual languages

| # | Prototype | Extracted principle | Strength | Risk |
|---:|---|---|---|---|
| 01 / R1 | Reference LED Dot Spectrum | 30 bands, discrete round LEDs, restrained pink | Closest literal match; cheap CPU path | Conventional without careful spacing |
| 02 | True LED Spectrum | 48 segmented levels and level colour | Clear energy and LED identity | Analyzer-like |
| 03 / R2 | Soft Round LED | 34 bands, smoothing, breathing room, halo | Premium evolution of R1 | Bright scenes need opacity lift |
| 04 | Monstercat Minimal | 64 slim bars under broad envelope | Music-video motion clarity | Familiar spectrum vocabulary |
| 05 | CAVA Smooth Bars | 44 heavily smoothed blocks | Stable long-form rhythm | Rectangular if unchanged |
| 06 | Rounded Neon Bars | 30 pill bars and round caps | Youthful neon graphic | Can dominate the scene |
| 07 | Dot + Glow Columns | 28 dot columns, additive halo | Atmospheric on dark footage | Glow can soften detail |
| 08 | Particle Spectrum | Deterministic band-following particles | Organic and unusual | Higher CPU/noise risk |
| 09 | Minimal Wave Dots | One smoothed dot path, no contour | Decorative, non-technical | Weak on bright footage |
| 10 / R3 | Tokyo Gradient Dots | 38 LEDs, pink-purple-cyan gradient | Most Tokyo-Chill-ready | Avoid rainbow drift |
| 11 | Soft Equalizer Lights | 24 blurred light pillars | Beautiful background integration | Low frequency readability |
| 12 | Designer Hybrid | Mound envelope, dots, sparse accents | Most authored silhouette | More tuning and QA |

## Why the strongest references look good

- Perceptual/log frequency aggregation prevents treble bins consuming the full width.
- Soft compression plus attack/release keeps quiet music visible without making every frame loud.
- LED quantization converts raw FFT into a designed object; 28–38 columns is closest to the user reference.
- Dot diameter and x/y gaps preserve scene space and are as important as amplitude.
- Three controlled colour stops outperform unrestricted hue cycling; highlights should be level-driven.
- A small core plus weak halo retains dot identity under Screen blend.
- Deterministic smoothing and peak falloff protect long-form stability and preview/export parity.

## Findings requiring user selection

- **Most reference-like:** Style 01 / R1, followed by Style 03 / R2.
- **Most beautiful:** Style 03 / R2 and Style 10 / R3.
- **Most hip / Tokyo Chill:** Style 10 / R3.
- **Most lightweight:** Style 01 / R1.
- **Best fit for current Python/OpenCV renderer:** Styles 01, 03, 07 and 10; no Node/Chromium runtime needed.
- **Dark:** Style 10; **mid-tone:** Style 03. Bright footage needs a small opacity/core-alpha increase.
- No winner is promoted. **USER SELECTION REQUIRED.**

## Top library inspirations

1. audioMotion-analyzer — True LED, gradients, spacing, smoothing (AGPL: reference-only).
2. wave.js — broad Canvas mode vocabulary.
3. monstercat-visualizer — lower-third music-video balance.
4. Cavalier — smooth configurable curves/bars.
5. Cavasik — spectrum aesthetics (GPL: reference-only).
6. audio-reactive-led-strip — energy-to-colour response.
7. clubber — musical band extraction.
8. HTML5_Audio_Visualizer — simple Canvas/Web Audio mapping.
9. butterchurn — palette timing and reactivity.
10. projectM — mature motion/palette reference; conditional review required.

## Production feasibility and risks

- LED/dot candidates map directly to ModernGL instancing and NumPy/OpenCV fallback.
- Avoid Chromium/Node runtime dependencies for offline, long-form Windows packaging.
- Particle/shader engines increase package size, determinism risk and CPU cost.
- GPL/AGPL/no-license sources remain design references; do not copy production source.
- Downloaded screenshots are internal comparison material, not distributable assets.

## Artifacts

- `visualizer_library_matrix.csv/json/md`
- `shortlist_top25.md/json`
- `shortlist_tokyo15.md/json`
- `library_reference_top20_01.png`, `library_reference_top20_02.png`
- 12 wave-only, 12 Mid, and 12 Dark MP4s
- Three 12-style contact sheets
