class OptionalAnalyzerUnavailable(RuntimeError):pass
def librosa_available():
    try:import librosa;return True
    except ImportError:return False
def analyze_librosa(samples,sample_rate):
    try:import librosa
    except ImportError as exc:raise OptionalAnalyzerUnavailable("Advanced librosa analysis is optional. Install requirements-advanced.txt.") from exc
    import numpy as np
    y=np.asarray(samples,dtype=np.float32)
    return {"onset_strength":librosa.onset.onset_strength(y=y,sr=sample_rate),"tempo":float(np.asarray(librosa.feature.tempo(y=y,sr=sample_rate)).reshape(-1)[0]),"spectral_centroid":librosa.feature.spectral_centroid(y=y,sr=sample_rate)[0],"spectral_rolloff":librosa.feature.spectral_rolloff(y=y,sr=sample_rate)[0]}
