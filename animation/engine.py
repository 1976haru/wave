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
        # Signature modes use a perceptual six-zone curve.  It deliberately
        # favours bass/low-mid content and keeps hi-hats from turning the calm
        # dotted baseline into a conventional full-height EQ.
        if str(self.t.get("renderer", "")).lower() in {"dot_matrix", "twin_dot_matrix", "dot_line_hybrid", "echo_dots", "stereo_signature"}:
            zone_weights = np.asarray(self.t.get("frequency_weights", [.85, 1.15, 1.10, .90, .70, .55]), np.float32)
            for positions, weight in zip(np.array_split(np.arange(len(values)), len(zone_weights)), zone_weights):
                values[positions] *= weight
            floor = np.clip(float(self.t.get("dot_floor", .07)), 0, .25)
            compression = max(.35, float(self.t.get("soft_compression", .72)))
            values = floor + (1.0-floor) * np.power(np.clip(values, 0, 1), compression)
            if self.t.get("sparse_columns"):
                # Stable, frequency-derived pillars: never random and identical
                # in preview/export for the same feature frame.
                rank = np.argsort(values)
                keep = np.zeros(len(values), np.float32)
                keep[rank[-max(3, len(values)//5):]] = 1.0
                values *= .28 + .72*keep
        smoothing = np.clip(float(self.t.get("smoothing", 0.15)), 0, .95)
        if len(values) > 2 and smoothing:
            values = (1-smoothing)*values + smoothing*np.convolve(values, [.25,.5,.25], mode="same")
        values = np.clip(values, 0, 1)
        if self.prev is None: self.prev = values
        else:
            retain = np.where(values > self.prev, np.clip(float(self.t.get("attack", .5)),0,1), np.clip(float(self.t.get("decay", .9)),0,1))
            self.prev = retain*self.prev + (1-retain)*values
        result={"values":self.prev.copy(),"bass":signals[0],"mid":signals[1],"high":signals[2],"onset":float(self.f["onset"][i]),"time":float(seconds)}
        if str(self.t.get("renderer","")).lower()=="stereo_signature":
            def delayed(ms,blend):
                index=max(0,i-int(round(float(ms)*fps/1000.0)));raw=np.resize(self.f["spectrum"][index].astype(np.float32),len(self.prev));floor=float(self.t.get("dot_floor",.07));raw=floor+(1-floor)*np.power(np.clip(raw,0,1),float(self.t.get("soft_compression",.7)));return np.clip((1-blend)*self.prev+blend*raw,0,1)
            result["left_values"]=delayed(self.t.get("left_delay_ms",20),.22)
            result["right_values"]=delayed(self.t.get("right_delay_ms",65),.30)
            result["left_onset"]=float(self.f["onset"][max(0,i-int(round(float(self.t.get("left_delay_ms",20))*fps/1000.0)))])
            result["right_onset"]=float(self.f["onset"][max(0,i-int(round(float(self.t.get("right_delay_ms",65))*fps/1000.0)))])
        return result
