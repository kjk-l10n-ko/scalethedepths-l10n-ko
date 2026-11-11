"""Build + install the Scale the Depths Korean patch.

Korean replaces the Japanese locale: the ja string tables get Korean text,
the ja TMP font (dynamic DotGothic16) gets Galmuri11-Bold source bytes with
its glyph cache cleared so TMP rasterizes Hangul at runtime.

Outputs patched files to out/ at game-relative paths, copies the pristine
originals used to backup/ (for the installer's zstd delta), and optionally
installs into the game (originals kept as *.orig).

usage: python3 scripts/build_patch.py [--game "<Scale the Depths install dir>"] [--no-install]
"""
import argparse, glob, json, os, shutil
import UnityPy
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AA_DIR = "Scale The Depths_Data/StreamingAssets/aa"
SUBDIR = "StandaloneWindows64"
AA = f"{AA_DIR}/{SUBDIR}"
TABLES = "localization-string-tables-japanese(ja)_assets_all.bundle"
FONTS = "localization-assets-japanese(ja)_assets_all.bundle"
EN_TABLES = "localization-string-tables-english(en)_assets_all.bundle"
CATALOG = "catalog.bin"
FONT = os.path.join(ROOT, "assets", "fonts", "Galmuri11-Bold.ttf")
CONTENTS = os.path.join(ROOT, "locales", "contents")
PRISTINE_FILES = (f"{AA}/{TABLES}", f"{AA}/{FONTS}", f"{AA_DIR}/{CATALOG}")


def original(game, name):
    """Pristine bundle: the .orig backup if we already installed once."""
    p = os.path.join(game, AA, name)
    return p + ".orig" if os.path.exists(p + ".orig") else p


def load_korean():
    ko = {}
    for f in sorted(glob.glob(os.path.join(CONTENTS, "*.json"))):
        for r in json.load(open(f, encoding="utf-8")):
            ko.setdefault(r["table"], {})[int(r["id"])] = r["ko"] or r["en"]
    return ko


def patch_tables(game, out):
    ko = load_korean()
    en_ids = {}
    for o in UnityPy.load(original(game, EN_TABLES)).objects:
        if o.type.name == "MonoBehaviour":
            t = o.read_typetree()
            en_ids[t["m_Name"].rsplit("_", 1)[0]] = [e["m_Id"] for e in t["m_TableData"]]
    env = UnityPy.load(original(game, TABLES))
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        t = o.read_typetree()
        name = t["m_Name"].rsplit("_", 1)[0]
        rows = {e["m_Id"]: e for e in t["m_TableData"]}
        for i in en_ids[name]:  # ja lacks a few en keys; add them
            rows.setdefault(i, {"m_Id": i, "m_Localized": "", "m_Metadata": {"m_Items": []}})
        for i, e in rows.items():
            if i in ko.get(name, {}):
                e["m_Localized"] = ko[name][i]
        t["m_TableData"] = list(rows.values())
        o.save_typetree(t)
    open(os.path.join(out, AA, TABLES), "wb").write(env.file.save(packer="lz4"))


def patch_font(game, out):
    data = open(FONT, "rb").read()
    tt = TTFont(FONT)
    upm, hh, os2 = tt["head"].unitsPerEm, tt["hhea"], tt["OS/2"]
    env = UnityPy.load(original(game, FONTS))
    for o in env.objects:
        if o.type.name == "Font":
            t = o.read_typetree()
            t["m_FontData"] = list(data)
            t["m_FontNames"] = ["Galmuri11"]
            o.save_typetree(t)
        elif o.type.name == "MonoBehaviour":
            t = o.read_typetree()
            fi = t["m_FaceInfo"]
            s = fi["m_PointSize"] / upm
            asc, desc = hh.ascent * s, hh.descent * s
            fi.update(m_FamilyName="Galmuri11", m_StyleName="Bold", m_UnitsPerEM=upm,
                      m_LineHeight=(hh.ascent - hh.descent + hh.lineGap) * s,
                      m_AscentLine=asc, m_DescentLine=desc, m_CapLine=os2.sCapHeight * s,
                      m_MeanLine=os2.sxHeight * s, m_SuperscriptOffset=asc, m_SubscriptOffset=desc,
                      m_UnderlineOffset=tt["post"].underlinePosition * s,
                      m_UnderlineThickness=tt["post"].underlineThickness * s)
            # drop DotGothic glyph cache: TMP refills it dynamically from the new font
            t["m_GlyphTable"], t["m_CharacterTable"], t["m_UsedGlyphRects"] = [], [], []
            t["m_FreeGlyphRects"] = [{"m_X": 0, "m_Y": 0, "m_Width": t["m_AtlasWidth"] - 1,
                                      "m_Height": t["m_AtlasHeight"] - 1}]
            t["m_FontFeatureTable"]["m_GlyphPairAdjustmentRecords"] = []
            o.save_typetree(t)
    open(os.path.join(out, AA, FONTS), "wb").write(env.file.save(packer="lz4"))


def patch_catalog(game, out):
    """Addressables verifies a per-bundle CRC stored in catalog.bin. Our
    rewritten bundles fail it, so zero the CRC (0 = skip verification).

    Binary catalog: each bundle has an options record
    [u32 hash-offset][u32 name-offset][u32 crc][u32 size]... where hash-offset
    points at the bundle's raw 16-byte Hash128. The CRC is a fixed-width uint,
    so zeroing it in place shifts nothing."""
    import re, struct
    src = os.path.join(game, AA_DIR, CATALOG)
    if os.path.exists(src + ".orig"):
        src += ".orig"
    cat = bytearray(open(src, "rb").read())
    patched = 0
    for target in (TABLES, FONTS):
        m = re.search(re.escape(target[:-len(".bundle")]).encode() + rb"_([0-9a-f]{32})", cat)
        assert m, f"{target} not found in {CATALOG}"
        raw = bytes.fromhex(m.group(1).decode())
        h = cat.index(b"bundle" + raw) + len(b"bundle")  # raw hash follows the path string
        refs = [r.start() for r in re.finditer(re.escape(struct.pack("<I", h)), cat) if r.start() % 4 == 0]
        assert len(refs) == 1, f"{target}: {len(refs)} options records, expected 1"
        cat[refs[0] + 8:refs[0] + 12] = b"\0\0\0\0"
        patched += 1
    assert patched == 2
    open(os.path.join(out, AA_DIR, CATALOG), "wb").write(cat)


def stage_pristine(game, dst):
    """Copy the untouched originals used by the delta installer to backup/."""
    for rel in PRISTINE_FILES:
        src = os.path.join(game, rel)
        if os.path.exists(src + ".orig"):
            src += ".orig"
        d = os.path.join(dst, rel)
        if not os.path.exists(d):
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(src, d)


def install(game, out):
    """Copy the built patch into the game (originals kept as *.orig)."""
    aa = os.path.join(game, AA_DIR)
    for name, sub in ((TABLES, SUBDIR), (FONTS, SUBDIR), (CATALOG, "")):
        src = os.path.join(out, AA_DIR, sub, name)
        dst = os.path.join(aa, sub, name)
        if not os.path.exists(dst + ".orig"):
            shutil.copy2(dst, dst + ".orig")
        shutil.copyfile(src, dst)
        print("installed", dst)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="/mnt/s/Installation/Steam/steamapps/common/Scale the Depths")
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--pristine", default=os.path.join(ROOT, "backup"))
    ap.add_argument("--no-install", action="store_true")
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, AA), exist_ok=True)
    patch_tables(a.game, a.out)
    patch_font(a.game, a.out)
    patch_catalog(a.game, a.out)
    stage_pristine(a.game, a.pristine)
    if not a.no_install:
        install(a.game, a.out)
