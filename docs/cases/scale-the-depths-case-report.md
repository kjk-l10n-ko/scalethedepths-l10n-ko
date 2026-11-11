# Scale the Depths — Korean Patch Case Report

## Summary
Unity 2022.3 (IL2CPP) + Unity Localization (Addressables) fishing game. The build ships 9 locales and no Korean slot, so Korean is applied by **replacing the Japanese (`ja`) locale bundles**. Text lives in Addressables MonoBehaviours (`localization-string-tables-*`), the Japanese TMP font is swapped for Galmuri11 Bold, and `catalog.bin` bundle CRCs are zeroed so Addressables accepts the rewritten bundles. **Status: complete** — 3,712 strings translated; title/publisher logos and Latin credit names intentionally left as-is.

## Engine & text storage
- **Unity 2022.3.x, IL2CPP, Windows** — bundles under `Scale The Depths_Data/StreamingAssets/aa/StandaloneWindows64/`.
- **Text:** `localization-string-tables-japanese(ja)_assets_all.bundle`, one `MonoBehaviour` per string table. Each has `m_TableData[]` rows `{m_Id, m_Localized, m_Metadata}`. Table names end with a suffix (`..._<hash>`); the English table supplies the full key set because the Japanese table lacks a few English IDs.
- **Font:** `localization-assets-japanese(ja)_assets_all.bundle` contains a `Font` asset (raw TTF bytes) and a TMP `MonoBehaviour` with `m_FaceInfo` + a pre-baked glyph/character cache from DotGothic16.
- **No drop-in locale folder / no Korean slot.** Catalog rebuild would renumber IDs; the shipped locale list is fixed, so patching the `ja` slot is the lowest-risk path.
- **Addressables catalog:** `Scale The Depths_Data/StreamingAssets/aa/catalog.bin` stores per-bundle CRC and hash. A modified bundle fails CRC validation unless its record is zeroed (0 = skip).

## Technique
1. **String tables** (`scripts/build_patch.py: patch_tables`)
   - Read English table to get the authoritative ID order.
   - Read the `ja` table, add missing English IDs as empty rows, then set `m_Localized` from `locales/contents/*.json` (`table`, `id`, `en`, `ko`; `ko || en` fallback).
   - Save with `env.file.save(packer="lz4")`.
2. **Font** (`patch_font`)
   - Replace the `Font` object's `m_FontData` with `assets/fonts/Galmuri11-Bold.ttf` and set `m_FontNames = ["Galmuri11"]`.
   - Recompute `m_FaceInfo` metrics (`m_UnitsPerEM`, ascent/descent, line height, cap/mean line, underline) from `head`/`hhea`/`OS/2`/`post` at the existing `m_PointSize`.
   - Clear `m_GlyphTable`, `m_CharacterTable`, `m_UsedGlyphRects` and kerning records; reset free rect to the full atlas. TMP then rasterizes Hangul dynamically at runtime.
3. **Catalog** (`patch_catalog`)
   - Find `bundle<Hash128>` path strings for both target bundles in `catalog.bin`.
   - The following 16-byte hash value also appears as a `uint32` offset in the bundle's options record; locate that aligned occurrence and zero the 4-byte CRC at `+8`. Assert exactly one record per bundle.
4. **Install** (`install`) — copy the three patched files over the game's copies, keeping `.orig` backups.

## Font / character-set handling
- DotGothic16 (original `ja` font) has no Hangul; Galmuri11 Bold is a 2.5 MB pixel TTF with full Hangul + Latin.
- TMP dynamic atlas generates glyphs on demand, so no atlas pre-baking is required; this is why the technique avoids texture work.
- Galmuri lacks Cyrillic, Han, and kana, so the language list's non-Korean names are shown with Korean names (영어/일본어/…) rather than native scripts.
- `scripts/qa.py` checks every final character against the font cmap (`FONT MISSING`), plus placeholders `{Token}`, `\n` counts, and untranslated rows.

## Pitfalls
| Symptom | Cause | Fix |
|---|---|---|
| Modified bundles rejected at startup | Addressables verifies catalog CRC | zero the bundle CRC in `catalog.bin` (`0` = skip) |
| CRC zeroing corrupted the catalog | binary record layout not parsed | options record is `[u32 hash-offset][u32 name-offset][u32 crc][u32 size]`; locate by the aligned hash-offset value and patch only bytes `+8..+12` |
| Japanese-only rows missing after patch | `ja` tables omit a few IDs the `en` table has | take ID order from the English bundle and `rows.setdefault(...)` |
| New font renders boxes / wrong metrics | stale TMP `m_FaceInfo` and cached DotGothic glyphs | recompute face metrics and clear glyph/character tables |
| Korean not selectable in the language row | game has no `ko` locale; patch uses the `ja` slot | in-game `설정 > 게임플레이 > 언어` select 한국어 once (setting is saved) |
| Title logo still English | logo and publisher marks are images | leave as-is (the Japanese release does the same) |

## Operational recipe
```bash
GAME="/mnt/s/Installation/Steam/steamapps/common/Scale the Depths"
# build (UnityPy + fontTools required), write out/ and backup/originals:
python3 scripts/build_patch.py --game "$GAME" --no-install
# or build + install into the game (keeps *.orig):
python3 scripts/build_patch.py --game "$GAME"
# content QA: untranslated / tokens / newlines / font coverage / short-string glossary
python3 scripts/qa.py --glossary locales/glossary.tsv
```
- Source of truth for text: `locales/contents/*.json`.
- `out/` mirrors the game-relative paths; `backup/` holds the pristine originals for the installer's zstd delta.
- Packaging: `scripts/build_installer.sh` (pipeline `make_payload.py`, `mode: zstd_delta`).
- Uninstall: restore `*.orig`, or Steam "verify integrity of game files".

## Tools used
| Script | Purpose |
|---|---|
| `scripts/build_patch.py` | patch ja string tables, font, catalog; stage `out/` + `backup/`; optional install |
| `scripts/qa.py` | translation/token/newline/font-coverage checks; glossary dump |
| `scripts/build_installer.sh` | delta payload + Nuitka installer via `tools-l10n-ko` |

## Verification status
- File-level: all 3,712 rows have non-empty `ko`; QA previously reported 0 problems.
- Visual in-game verification of the published build is not re-run in this repo migration.
