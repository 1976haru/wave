from pathlib import Path
import numpy as np
from template_system import load_template
from render.renderer import CPURenderer, RendererFactory

def _state():
    return {"values": np.abs(np.sin(np.linspace(0, 9, 64))) * .55 + .2}

def test_special_renderer_types_are_present():
    assert {load_template(Path("templates") / name).get("renderer") for name in ("23_chill_ribbon.json","38_spectrum_ring.json","40_radial_wave.json")} == {"ribbon","ring","radial"}

def test_ribbon_cpu_has_visible_alpha():
    image=CPURenderer().render_rgba(320,180,_state(),load_template("templates/23_chill_ribbon.json")); assert image.shape==(180,320,4) and image[:,:,3].max()>0

def test_ring_cpu_has_visible_alpha():
    image=CPURenderer().render_rgba(320,180,_state(),load_template("templates/38_spectrum_ring.json")); assert image[:,:,3].max()>0 and np.count_nonzero(image[:,:,3])>100

def test_radial_cpu_has_visible_alpha():
    image=CPURenderer().render_rgba(320,180,_state(),load_template("templates/40_radial_wave.json")); assert image[:,:,3].max()>0

def test_gpu_request_special_renderer_falls_back_safely():
    image=RendererFactory.create("AUTO").render_rgba(160,90,_state(),load_template("templates/40_radial_wave.json")); assert image.shape==(90,160,4)

def test_showcase_thumbnails_are_visible():
    from template_system.thumbnails import get_thumbnail
    from PIL import Image
    for name in ("23_chill_ribbon.json","38_spectrum_ring.json","40_radial_wave.json"):
        image=np.asarray(Image.open(get_thumbnail(load_template(Path("templates")/name))[0])); assert image.shape[2]==4 and image[:,:,3].max()>0
