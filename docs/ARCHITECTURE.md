# Architecture

Music Wave Studio v0.5.2 keeps four production layers independent: cached audio analysis, time-based animation, true-RGBA rendering, and reusable templates.

## Interactive path

`ui/roi_widget.py` maps a letterboxed, DPI-independent Qt selection rectangle back to exact source-image coordinates. The dialog darkens the unselected area and supports reset, apply, and cancel. Reference analysis runs in a worker and presents extracted values before template application.

`preview/` renders 960×540 frames directly from cached features. `FrameScheduler` derives the desired frame index from the authoritative Qt audio clock. It drops obsolete indices, jumps to the newest time, resets on seek/backward time, and records rendered/dropped frames and maximum drift. No temporary preview video or repeat FFT is used.

## Rendering

The CPU renderer covers bars, connected lines, dots, mirror, gradient, opacity, roundness, shadow, and glow. The ModernGL renderer uses instanced bars/dots, a connected triangle-strip polyline, an RGBA offscreen framebuffer, horizontal and vertical GLSL blur passes, and a GPU composite pass. AUTO catches both initialization and render-time shader/context failure and permanently switches that renderer instance to CPU.

## Validation

- `tools/system_check.py`: Python/dependencies/GPU context/FFmpeg encoders.
- `tools/validate_audio.py`: up to 15 tracks by default, decode metadata, cold/warm cache, memory, preview and render estimates, JSON/TXT report.
- `tools/validate_preview.py`: deterministic 10/30/60 second scheduling sessions.
- `tools/benchmark_render.py`: CPU/GPU frame generation and FFmpeg encode timing for preview, landscape, and portrait.
- `tools/export_smoke.py`: codec, resolution, FPS, alpha, audio, and one-frame duration tolerance.
- `tools/create_capcut_test.py`: manual CapCut compatibility assets and checklist.

CPU visual baselines cover bars, line, dot, mirror, gradient, glow, opacity, and roundness. GPU comparison activates only when a ModernGL context exists.
