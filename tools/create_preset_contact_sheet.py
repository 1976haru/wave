from pathlib import Path
import sys, json
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from template_system import list_templates
from template_system.thumbnails import get_thumbnail

def resolve_font(size=18):
    candidates=[Path(r"C:\Windows\Fonts\malgun.ttf"),Path(r"C:\Windows\Fonts\malgunsl.ttf"),Path(r"C:\Windows\Fonts\segoeui.ttf")]
    for path in candidates:
        if path.exists():
            try:return ImageFont.truetype(str(path),size)
            except OSError: pass
    return None

items=[data for _,data in list_templates("templates")]
cols,cell_w,cell_h=4,320,190; rows=(len(items)+cols-1)//cols
sheet=Image.new("RGB",(cols*cell_w,rows*cell_h),"#11151c"); draw=ImageDraw.Draw(sheet); font=resolve_font(18); small=resolve_font(14)
for i,data in enumerate(items):
    x,y=(i%cols)*cell_w,(i//cols)*cell_h
    try:
        thumb_path,_=get_thumbnail(data,width=280,height=135); thumb=Image.open(thumb_path).convert("RGBA"); bg=Image.new("RGBA",thumb.size,"#252d38"); bg.alpha_composite(thumb); sheet.paste(bg.convert("RGB"),(x+20,y+8))
    except Exception: pass
    ko=str(data.get("name_ko") or data.get("name_en") or data.get("name") or data.get("id")); en=str(data.get("name_en") or data.get("name") or data.get("id")); renderer=str(data.get("renderer","bars")).upper()
    draw.text((x+20,y+146),ko[:28],fill="#f4f7fa",font=font); draw.text((x+20,y+168),f"{en[:22]}  ·  {renderer}",fill="#b7c0cb",font=small)
sheet.save("validation_results/v079_preset_contact_sheet.png")
print("validation_results/v079_preset_contact_sheet.png")
