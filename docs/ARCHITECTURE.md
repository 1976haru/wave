# Architecture

Music Wave Studio v0.6 retains four independent production layers: cached audio analysis, time-based animation, true-RGBA design rendering, and reusable templates.

## Preview concurrency

Qt Multimedia is the authoritative audio clock. `FrameScheduler` selects the newest audio frame index and drops obsolete indices. The GUI writes frame requests into `LatestFrameMailbox`, a thread-safe single-slot mailbox. `PreviewRenderWorker` owns AnimationEngine and the CPU/ModernGL renderer in its QThread, including the OpenGL context. The GUI receives completed NumPy RGBA frames only; stale results beyond the current audio time tolerance are discarded.

## Rendering and quality

The ModernGL path provides instanced bars/dots, connected line triangle strips, RGBA framebuffer rendering, horizontal/vertical GLSL blur, and GPU composite. AUTO handles initialization and runtime shader/context errors by switching to CPU.

CPU glow is profiled and quality-aware. PREVIEW uses a quarter-resolution glow buffer, BALANCED uses half resolution, and QUALITY uses full resolution. Gradient LUTs are cached. Export writes contiguous NumPy memory directly to FFmpeg without a `tobytes()` frame copy. Animation, renderer, pipe blocking, and final encoder wait are timed separately to identify Renderer versus Encoder bottlenecks.

## Batch safety

`BatchRunner` writes `batch_state.json` through an atomic temporary replacement. A stale `rendering` entry becomes pending on restart. Completed outputs may be skipped, while failed and cancelled entries remain visible. `error_report.json` is preserved.

## Distribution

`music_wave_studio.spec` bundles templates, smoke resources, PyAV, ModernGL, OpenCV, and the Qt modules discovered from actual imports. `core.resource_path` resolves source and PyInstaller `_MEIPASS` resources. FFmpeg remains an explicit system PATH dependency.

## Validation tools

- `system_check.py`: dependencies, GPU context, and encoders.
- `validate_audio.py`: 15 tracks by default, metadata, cold/warm cache, CPU/GPU estimates, memory, JSON/TXT.
- `validate_preview.py`: 10/30/60 second scheduler validation.
- `profile_render.py`: animation and CPU renderer stages.
- `benchmark_render.py`: CPU/GPU generation, memory, FFmpeg encoding, and one-hour estimates.
- `export_smoke.py`: resolution, FPS, alpha, audio, and duration regression.
- `create_capcut_test.py`: three manual CapCut test assets and checklist.

CPU visual baselines cover eight renderer features. GPU perceptual comparison activates whenever a ModernGL context is available.
