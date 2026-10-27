"""Comprehensive i18n Dictionary Reconciliation Audit Tool."""

import os
import re
import sys
from pathlib import Path

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.i18n import STRINGS

def audit_i18n():
    code_keys = set()
    pat = re.compile(r'get_text\(\s*["\']([^"\']+)["\']')
    label_pat = re.compile(r'_label\(\s*["\']([^"\']+)["\']')

    for folder in ['core', 'ui']:
        for root, dirs, files in os.walk(folder):
            for f in files:
                if f.endswith('.py'):
                    with open(os.path.join(root, f), 'r', encoding='utf-8') as fp:
                        for line in fp:
                            for m in pat.finditer(line):
                                k = m.group(1).strip()
                                if k:
                                    code_keys.add(k)
                            for m in label_pat.finditer(line):
                                k = m.group(1).strip()
                                if k:
                                    code_keys.add(k)

    string_keys = set(STRINGS.keys())

    missing_in_strings = code_keys - string_keys
    missing_in_en = {k for k, v in STRINGS.items() if 'en' not in v or not v['en']}
    missing_in_ko = {k for k, v in STRINGS.items() if 'ko' not in v or not v['ko']}

    suspicious_en = {k: v.get('en') for k, v in STRINGS.items() if v.get('en') and (v['en'] == k or re.match(r'^(btn_|lbl_|txt_|menu_|title_)', v['en']))}
    suspicious_ko = {k: v.get('ko') for k, v in STRINGS.items() if v.get('ko') and (v['ko'] == k or re.match(r'^(btn_|lbl_|txt_|menu_|title_)', v['ko']))}

    print("=" * 60)
    print("           i18n DICTIONARY AUDIT REPORT               ")
    print("=" * 60)
    print(f"Total keys in STRINGS: {len(string_keys)}")
    print(f"Total keys invoked in code: {len(code_keys)}")
    print(f"\n[!] Keys invoked in code but MISSING from STRINGS ({len(missing_in_strings)}):")
    for k in sorted(missing_in_strings):
        print(f"  - {k}")
        # Search which files invoke it
        for folder in ['core', 'ui']:
            for root, dirs, files in os.walk(folder):
                for f in files:
                    if f.endswith('.py'):
                        path = os.path.join(root, f)
                        with open(path, 'r', encoding='utf-8') as fp:
                            for idx, line in enumerate(fp):
                                if f'"{k}"' in line or f"'{k}'" in line:
                                    print(f"      {path}:{idx+1}: {line.strip()[:80]}")

    print(f"\n[!] Keys missing English translation ({len(missing_in_en)}):")
    for k in sorted(missing_in_en):
        print(f"  - {k}")

    # Scan each file specifically for get_text
    file_missing = {}
    for folder in ['core', 'ui']:
        for root, dirs, files in os.walk(folder):
            for f in files:
                if f.endswith('.py'):
                    path = os.path.join(root, f)
                    with open(path, 'r', encoding='utf-8') as fp:
                        content = fp.read()
                        matches = pat.findall(content)
                        miss = [m for m in matches if m.strip() and m not in STRINGS]
                        if miss:
                            file_missing[path] = set(miss)

    print("\n--- Files invoking missing get_text keys ---")
    for p, keys in file_missing.items():
        print(f"  {p}: {keys}")

    print(f"\n[!] Suspicious English values ({len(suspicious_en)}):")
    for k, v in sorted(suspicious_en.items()):
        print(f"  - {k}: {v}")

    print(f"\n[!] Suspicious Korean values ({len(suspicious_ko)}):")
    for k, v in sorted(suspicious_ko.items()):
        print(f"  - {k}: {v}")

    return {
        "missing_in_strings": missing_in_strings,
        "missing_in_en": missing_in_en,
        "missing_in_ko": missing_in_ko,
        "suspicious_en": suspicious_en,
        "suspicious_ko": suspicious_ko,
    }

if __name__ == "__main__":
    audit_i18n()
