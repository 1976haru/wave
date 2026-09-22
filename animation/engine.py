from __future__ import annotations
import numpy as np

class AnimationEngine:
    """Sample cached analysis at t and apply frequency-aware dynamics."""
    def __init__(self, features, template): self.f, self.t, self.prev = features, template, None
    def reset(self): self.prev = None
    def sample(self, seconds):
        fps = float(self.f["fps"][0]); i = min(len(self.f["spectrum"]) - 1, max(0, int(seconds * fps)))
        values = self.f["spectrum"][i].astype(np.float32, copy=True)
        signals = (float(self.f["bass"][i]), float(self.f["mid"][i]), float(self.f["high"][i]))
        weights = tuple(float(self.t.get(k, 1.0)) for k in ("bass_weight", "mid_weight", "high_weight"))
        for positions, signal, weight in zip(np.array_split(np.arange(len(values)), 3), signals, weights):
            values[positions] *= max(0.0, weight) * (0.65 + 0.35 * signal)
        values *= float(self.t.get("response", 1.25)) * (0.7 + 0.3 * float(self.f["rms"][i]))
        values += float(self.f["onset"][i]) * float(self.t.get("onset_boost", 0.1))
        smoothing = np.clip(float(self.t.get("smoothing", 0.15)), 0, .95)
        if len(values) > 2 and smoothing:
            values = (1-smoothing)*values + smoothing*np.convolve(values, [.25,.5,.25], mode="same")
        values = np.clip(values, 0, 1)
        if self.prev is None: self.prev = values
        else:
            retain = np.where(values > self.prev, np.clip(float(self.t.get("attack", .5)),0,1), np.clip(float(self.t.get("decay", .9)),0,1))
            self.prev = retain*self.prev + (1-retain)*values
        return {"values": self.prev.copy(), "bass": signals[0], "mid": signals[1], "high": signals[2], "onset": float(self.f["onset"][i])}
