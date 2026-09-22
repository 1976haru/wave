def user_message(exc):
    text=str(exc);lower=text.lower()
    if "ffmpeg" in lower:return "FFmpeg is not available. Set its path in Settings or install it on PATH."
    if "permission" in lower:return "The output folder is not writable. Choose another folder."
    if "space" in lower:return "The output disk may be full. Free space and retry."
    if "shader" in lower or "context" in lower:return "GPU rendering failed. AUTO mode will use the CPU renderer."
    if "decode" in lower or "codec" in lower:return "The audio file could not be decoded or uses an unsupported codec."
    return text or exc.__class__.__name__
