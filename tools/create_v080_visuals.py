from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
import numpy as np
from template_system import load_template
from render.renderer import CPURenderer
ids=["09_classic_white_bars","10_warm_cream_line","12_gentle_mirror","11_vintage_meter","18_tokyo_neon","19_midnight_pink","23_chill_ribbon","27_room_groove","28_paris_thin_line","29_champagne_gold","31_blue_jazz","34_piano_room"]
font=ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf",18) if Path(r"C:\Windows\Fonts\malgun.ttf").exists() else None
sheet=Image.new("RGB",(720,760),"#11151c"); draw=ImageDraw.Draw(sheet); vals=np.abs(np.sin(np.linspace(0,np.pi*3,64)))*.55+.18; vals[::7]=.9
for i,ident in enumerate(ids):
    t=load_template(Path("templates")/(ident+".json")); rgba=CPURenderer().render_rgba(220,120,{"values":vals},dict(t,_quality="QUALITY",_glow_scale=.5)); im=Image.fromarray(rgba,"RGBA"); x=(i%3)*240+10;y=(i//3)*185+8; bg=Image.new("RGBA",im.size,"#252d38");bg.alpha_composite(im);sheet.paste(bg.convert("RGB"),(x,y));draw.text((x,y+125),str(t.get("name_en",ident)),fill="#f4f7fa",font=font);draw.text((x,y+148),str(t.get("renderer","bars")).upper(),fill="#8ec5ff",font=font)
sheet.save("validation_results/v080_flagship_12.png")
for ident in ["18_tokyo_neon","23_chill_ribbon","38_spectrum_ring","40_radial_wave"]:
 t=load_template(Path("templates")/(ident+".json")); rgba=CPURenderer().render_rgba(960,540,{"values":vals},dict(t,_quality="QUALITY",_glow_scale=.5)); Image.fromarray(rgba,"RGBA").save(f"validation_results/v080_{ident}.png")
print("done")

