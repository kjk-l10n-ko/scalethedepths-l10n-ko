"""QA for the Scale the Depths Korean patch content.

Checks every locales/contents/*.json row and the shipped font:
  * translated       -- no empty `ko` for non-empty `en`
  * placeholders     -- every {Token} in `en` survives in `ko`
  * newlines         -- \n count preserved
  * font coverage    -- every char of final text exists in the patched font
  * glossary         -- dump the names/short labels (en -> ko), for consistency reviews

usage: python3 scripts/qa.py [--glossary locales/glossary.tsv]
"""
import argparse, glob, json, os, re, sys
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "assets", "fonts", "Galmuri11-Bold.ttf")


def rows():
    for f in sorted(glob.glob(os.path.join(ROOT, "locales", "contents", "*.json"))):
        for r in json.load(open(f, encoding="utf-8")):
            r["file"] = os.path.basename(f)
            yield r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glossary")
    a = ap.parse_args()
    cmap = set(TTFont(FONT).getBestCmap())
    problems, short = 0, []
    for r in rows():
        en, ko = r["en"], r["ko"]
        tag = f"{r['file']}:{r['table']}:{r['id']}"
        if en.strip() and not ko.strip():
            print("UNTRANSLATED", tag, repr(en[:60])); problems += 1; continue
        if a.glossary and len(en.split()) <= 4:
            short.append((r["table"], en, ko))
        if en.strip() == ko.strip() and re.search(r"[A-Za-z]{3}", en):
            pass  # identical Latin text is legitimate (names, version tags)
        for tok in set(re.findall(r"\{[^}]*\}", en)):
            if tok not in ko:
                print("TOKEN LOST", tag, tok, repr(ko[:60])); problems += 1
        if en.count("\n") != ko.count("\n"):
            print("NEWLINE DIFF", tag, en.count("\n"), ko.count("\n"), repr(ko[:60])); problems += 1
        for ch in ko:
            if ch != "\n" and ord(ch) not in cmap:
                print("FONT MISSING", tag, repr(ch), repr(ko[:60])); problems += 1
    if a.glossary:
        with open(a.glossary, "w", encoding="utf-8") as fh:
            for table, en, ko in sorted(short):
                fh.write(f"{table}\t{en}\t{ko}\n")
        print("glossary rows", len(short), "->", a.glossary)
    print("PROBLEMS", problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
