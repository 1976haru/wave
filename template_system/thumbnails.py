from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image
from render.renderer import CPURenderer
def template_hash(template):return hashlib.sha256(json.dumps(template,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def thumbnail_path(template,cache_dir="cache/thumbnails"):return Path(cache_dir)/f"{template_hash(template)}.png"
def get_thumbnail(template,cache_dir="cache/thumbnails",width=180,height=72):
    target=thumbnail_path(template,cache_dir)
    if target.exists():return target,True
    target.parent.mkdir(parents=True,exist_ok=True);values=np.abs(np.sin(np.linspace(0,np.pi*3,36)))*.8+.1;rgba=CPURenderer().render_rgba(width,height,{"values":values},dict(template,_quality="PREVIEW"));Image.fromarray(rgba,"RGBA").save(target);return target,False
