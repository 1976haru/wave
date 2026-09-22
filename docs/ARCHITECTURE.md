# Architecture

Music Wave Studio keeps four layers independent:

1. `audio/` decodes with PyAV first and FFmpeg second. It computes all frame-aligned FFT, RMS, onset, bass, mid and high arrays once, then stores `cache/<content-and-settings-sha256>.npz`.
2. `animation/` samples cached arrays at time `t` and applies response, attack, decay, spatial smoothing, onset boost and bass/mid/high weights.
3. `render/` produces true RGBA. CPU drawing maintains alpha independently; ModernGL uses instanced bars and an RGBA framebuffer. `AUTO` catches GPU initialization failure and selects CPU.
4. `template_system/` owns v0.5 defaults, JSON persistence, and v0.3/v0.4 key migration.

`reference/` converts up to five images or a 5–10 second clip into template tendencies. `pipeline/` handles FFmpeg export, benchmark logs, cancellation and failure-isolated batches. `app.py` is only GUI orchestration; analysis and final rendering run in workers. Preview uses a cached 24 fps analysis and renders one representative frame at 640×360 instead of a full video.

Exports are H.264 MP4 (black background blend fallback), VP9 WebM alpha, and ProRes 4444 MOV alpha. FFmpeg `-shortest` keeps muxed duration bounded by the audio stream.
