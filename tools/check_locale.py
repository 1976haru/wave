from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ui.locale import TRANSLATIONS

def check_locale():
    errors=[]
    for language,values in TRANSLATIONS.items():
        for key,value in values.items():
            if not isinstance(value,str) or not value.strip():errors.append(f"{language}:{key}: empty")
            if "??" in value or "\ufffd" in value:errors.append(f"{language}:{key}: corrupted")
            if value==key:errors.append(f"{language}:{key}: key exposed")
    return errors

if __name__=="__main__":
    errors=check_locale();print("PASS" if not errors else "\n".join(errors));raise SystemExit(bool(errors))
