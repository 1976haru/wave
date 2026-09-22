# Architecture

Music Wave Studio v0.5.1 keeps four production layers independent:

1. `audio/` prefers PyAV, falls back to FFmpeg, computes frame-aligned FFT/RMS/onset/bass/mid/high once, and stores `cache/<content-and-settings-sha256>.npz`.
2. `animation/` samples cached arrays at time `t` and applies attack, decay, spatial smoothing, onset boost, and bass/mid/high weights.
3. `render/` interprets the same template for CPU and ModernGL RGBA renderers. Bars, line, dot, mirror, gradient, opacity, roundness and glow share the same geometry/color rules. AUTO isolates GPU initialization failure and selects CPU.
4. `template_system/` owns v0.5.1 defaults, JSON persistence, v0.3/v0.4 key migration, the built-in gallery, and user templates.

`preview/` is a separate 960×540/24 fps frame-at-time engine. It reuses analysis cache, re-samples cached spectrum when the band count changes, and never renders a temporary video. Qt Multimedia supplies audio time; the UI requests `AnimationEngine(t) → Renderer` frames on a 24 fps timer.

`reference/` analyzes up to five images with optional ROI and maps dominant color, bars, gaps, geometry, glow, and symmetry to template fields. Video sampling maps 5–10 seconds of motion energy and persistence to attack/decay/smoothing.

`pipeline/` supports H.264 MP4, VP9 WebM alpha, ProRes 4444 MOV alpha, benchmark data, cancellation, and failure-isolated batches. `tools/validate_audio.py` validates user libraries without checking media into Git; `tools/export_smoke.py` performs short end-to-end codec validation.

`app.py` is only the application entry point. `ui/` owns the dark Media/Reference/Templates, live Preview, Design/Effects/Export interface and delegates long analysis/render/reference operations to QThread workers.
