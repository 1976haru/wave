import json
from pathlib import Path
from template_system import load_template

def test_signature_families_are_complete():
    files=sorted(Path('templates').glob('5*_signature_*.json'))
    assert len(files)==9
    data=[load_template(p) for p in files]
    assert {d['category'] for d in data}=={'signature_dual','signature_his','signature_her'}
    assert all(d.get('name_ko') and d.get('description_ko') for d in data)

def test_signature_renderers_are_supported():
    assert {load_template(p)['renderer'] for p in Path('templates').glob('5*_signature_*.json')} <= {'bars','line','ribbon'}

def test_signature_catalog_and_main_choices_exist():
    report=json.loads(Path('validation_results/v0829_signature/v0829_signature_report.json').read_text(encoding='utf-8'))
    assert len(report['presets'])==9
    assert set(report['main_presets'])=={'MAIN_DUAL_STORY','MAIN_HIS_STORY','MAIN_HER_STORY'}
