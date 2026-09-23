from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from template_system import list_templates
from template_system.thumbnails import get_thumbnail
out = Path("validation_results/preset_contact_sheet.png")
items = [data for _, data in list_templates("templates")]; cols, cell_w, cell_h = 5, 240, 120
rows = (len(items) + cols - 1) // cols
sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "#11151c"); draw = ImageDraw.Draw(sheet)
for i, data in enumerate(items):
    x, y = (i % cols) * cell_w, (i // cols) * cell_h
    try:
        thumb = Image.open(get_thumbnail(data)).convert("RGBA").resize((220, 78)); sheet.paste(thumb, (x + 10, y + 6), thumb)
    except Exception: pass
    label = str(data.get("name_ko") or data.get("name_en") or data.get("name") or data.get("id")); draw.text((x + 10, y + 88), label[:28], fill="#f4f7fa")
sheet.save(out); print(out)

