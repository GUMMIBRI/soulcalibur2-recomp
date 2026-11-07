# FR-021: a native-looking Video Settings label

Research checkpoint: November 6, 2026. Read-only source, existing inventory and
bounded executable/texture-header inspection. Only this report was written.
No asset extraction/dump, image generation, runtime patch, game execution,
console operation or Git operation was performed. Boot stability remains the
main implementation priority. This is not a claim that FR-021 is implemented.

## Result and recommended route

SC2 has both texture-based UI drawing and original text/font infrastructure.
The evidence does **not yet establish whether the visible Options labels are
baked words, atlas glyphs or native string rendering**. It does establish
specific original Options strings/descriptors and original sprite/2D-layer
hooks worth tracing. Do not infer the Options font from character-select names.

Preferred sequence:

1. Trace the existing **Display Settings** item to its actual draw resource and
   input/state callback. If it uses an original text routine and usable font,
   render the new label through that routine with the same style/metrics.
2. If the item is baked artwork, compose a new word-label from verified original
   glyph pixels or the actual original atlas, retaining its material/blend and
   normal/focus appearance. Render a private offline comparison before calling
   the result matching; do not substitute a visually similar AI-generated font.
3. Treat entry/navigation implementation separately from label artwork. A new
   texture or changed ASCII string alone does not create an Options item,
   controller focus, selection sound, pause ownership or correct settings logic.

An existing **Display Settings** entry is a better native starting point than
inventing a new generic overlay appearance. Whether it should be extended or a
neighboring Video Settings item added is a product/integration decision after
its current behavior is known. Do not remove original controls by assumption.

## Proven original-code and asset leads

Addresses below are specific to the supported USA original-Xbox executable;
never transplant them to PAL/another build without that build's mapping.
The small inspections were reads from the existing owned XBE in private/disc,
and existing root.olk inventory/source. No original bytes enter this report.

| Lead | Verified observation | What it does not prove |
| --- | --- | --- |
| Options strings | Actual executable ASCII strings: `Sound Settings` at VA `0x17c3ec`, `Display Settings` at `0x17c3fc`, `Controller Settings` at `0x17c410`, `Game Settings` at `0x17c424`, `Options` at `0x17c558`. They occur among other mode/menu titles. | Existence of a string does not establish that the visible English title is drawn from it. It could serve a descriptor, debug/name or voice/resource association. No string replacement was attempted. |
| Descriptor pointers | Display's string pointer occurs at `0x17bb70`; related title pointers occur at `0x17bb38`, `0x17bb54` and `0x17bb8c`, separated by `0x1c` in this table region. Neighboring data includes state-like IDs, resource-like values and the common code pointer `0x77160`. | Exact struct field meanings and the complete Options table start/length are not recovered. Do not add rows or patch constants based only on the observed stride. |
| A useful false lead to avoid | Display's neighboring resource-like value has low index `0xa8`. Existing root inventory identifies `/2/168` as `mmx`, as do nearby candidate indices `/2/145`, `/2/167`, `/2/175`. | This is not evidence of an Options word texture at that index; these entries are sound-container candidates. A low resource number must not be treated as a VXT texture ID. |
| Font resources | Original executable names `temp\gt2_kanjifont.vxt` and `temp\gt2_kanjiinfo.bin`, via pointers at `0x190688` and `0x190684`; nearby mapping data includes Japanese/Shift-JIS-looking byte tables. Original function `0x157f0` consumes these pointers and calls `0x14800`. Its alternate path accepts supplied object pointers via `0x157c0`. | This establishes a font-loading candidate, not a proven original Options font or a ready public text-draw API. `temp` paths may concern a debug/auxiliary facility. No such loose font file was found/created, and no font image or metrics were visually inspected. |
| Select-name glyphs | `runtime/sc2_guest.cpp` identifies `kGlyphNames = 0x1a2450`, and `ApplyGuestRoster` installs a guest profile's name string there. `docs/guests.md` documents the gold select-name glyph string and profile packing. | This is character select. It neither supplies a general ASCII font nor identifies Options typography/normal/highlight behavior. |
| Menu sprite draw | `runtime/sc2_hooks.c::sprite_draw` wraps original `0x2abc0`. Existing comments/code identify center x/y, four-corner UVs at `+0x10..+0x2c`, and half-size at `+0x30/+0x34` in 640×448 logical units. The current grid-panel patch reuses/crops original texture pieces. | This proves original UI sprite composition is possible. The inspected special case is character-select panel geometry, not a verified Options label draw. |
| 2D layer and boxes | `layer_2d` wraps `0x331b0`, whose entries are dispatched through table `0x19bdc0`; `box_fill`/`box_frame` wrap `0x2ed80`/`0x2ec90`. | Useful native rendering/probe boundaries, not the Options item/state callback. Do not hook every UI draw or suppress base layers to fake an integrated menu. |
| Existing UI banks | Existing read-only OLNK inventory has 516 `/2` entries. `/2/0` is VXT v2 with 40 textures; `/2/8` is VXT v2 with 18. Bounded header reads confirm a mix of P8/DXT banks, with logical versus stored texture dimensions. | There are no semantic filenames in the OLNK. Neither bank nor any texture was identified visually as the Options label sheet. `/2/5` and `/2/9`/`/2/10` already have character-icon roles documented in the guest converter. Do not relabel all UI banks as fonts. |

The initial metadata interpretation was checked against the actual current
`tools/textures/build_map.py` and `tools/guests/textures.py` layouts: VXT v2
texture records are `0x24` bytes at bank `+0x14`, with logical dimensions at
record `+0x0c`, payload offset `+0x10`, format `+0x14`, stored dimensions `+0x18`
and mip count `+0x1c`. An earlier docstring shorthand is not sufficient to
implement a new reader. Examples from the bounded header inspection:
`/2/8` texture 1 has logical 344×32 stored in 512×32, texture 3 logical 320×96
stored in 512×128; these dimensions make them UI-sheet candidates only, not
identified English labels. Correct cropping must preserve logical dimensions.

## Existing tools and missing tooling

- `guest/olnk.h/.cpp`: `Olnk::child`, `entry_size`, `bytes` and `pack_parts`
  navigate numbered containers/packs. `guest/discs.*` can supply readers from
  existing extracted input or disc files. Reuse bounded reads; no duplicate ISO
  or full archive extraction is required for one UI entry.
- `tools/imports/olk_inventory.py` and the existing private
  `import-inventory/sc2-xbox-root.json` provide structural paths, sizes and
  prefixes. The tool is an inventory, not an image-label recognizer.
- `tools/guests/olnk.py` is the Python archive counterpart.
  `tools/guests/textures.py::p8_texture` can read a P8 bank texture, while
  `replace_p8`/`append_p8` and the C++ `guest/textures.*` counterparts are existing
  private-conversion building blocks. Use actual palette alpha, swizzle and
  dimensions; do not reinterpret P8 pixels as raw RGBA.
- `tools/textures/build_map.py::XboxTexture` and `xbox_textures` describe existing
  Xbox texture interpretation and hashing. Current HD replacement identities
  are hashes of native guest texture bytes (plus palette for P8), not OLK paths.
- `guest/tool.cpp` / `sc2_guest.exe` rebuild supported guest rosters. They are
  not a general UI texture atlas exporter or text authoring interface.
- `runtime/sc2_menu.cpp` is the existing host menu/settings bridge. Styling or
  changing its captions is not equivalent to adding an original guest Options
  row with original transitions/sounds/input ownership.
- The bundled xboxrecomp `src/nv2a/font_atlas_data.h` and menu pushbuffer samples
  are toolkit/reference-title material. They are not evidence of SC2's Options
  font and must not be used merely because they are called a font atlas.

No new asset extractor, menu font API or generic font metrics table has been
implemented by this task. A bounded UI image/atlas inspector and exact draw-call
association remain the next discovery step.

## Native-font branch: conditions before using it

Recover the actual Options draw caller and establish that its arguments select
a text string rather than a baked-texture resource. Identify encoding/control
codes, font resource/atlas, glyph metrics/kerning, x/y/scale, color/opacity,
normal versus focused state, texture/sampler filtering and clipping. Verify
all glyphs in **Video Settings**, including case and the space. An existing
character-select glyph sequence is not necessarily reusable by this caller.

If the original renderer is generic and font coverage is present, supply a
properly encoded private guest string and invoke the existing text draw through
the correct calling convention/object lifetime. Preserve global render state
and frame input ownership. Do not call the original routine from an arbitrary
host overlay thread or assign a new meaning to an unverified descriptor field.

If a native font can match the existing title exactly, this route preserves
its normal/focus treatment and can cover changing values (1×–8×, On/Off, FSR
strength) without pre-baking every value. Unknown glyphs, number formatting and
actual resolution-setting applicability still need explicit handling.

## Baked-word branch: original-pixel composition

After identifying the actual source sheet or original font atlas, collect only
the required small original regions and their metrics. Compose **Video
Settings** from those pixels; use the existing **Settings** suffix when its
style and state match. Obtain the remaining letters from the same verified
font/style, not unrelated character-select or debug-font artwork. Preserve
baseline, spacing, outline/shadow, antialiasing and transparent padding.
Never stretch an entire existing word to approximate a different one.

Determine whether highlight/focus comes from vertex tint/alpha, a separate
sprite/effect or a distinct texture. If normal/focus use the same pixels, reuse
the game's modulation; if separate artwork exists, make both from corresponding
source states. Preserve selection pulse/animation and disabled state separately.

Keep the label's logical size and original menu alignment in 640×448 units;
retain its backing texture's required power-of-two storage and UV rectangle.
Do not bake a panel/highlight box into the word texture if the game draws it
separately. A transparent BGRA8 DDS can preserve alpha for a private host-side
prototype; original VXT/P8 or appropriate DXT5 output may be needed for the
chosen native resource path. Avoid DXT1 when its one-bit alpha would damage
soft letter edges. Correct premultiplied/straight-alpha behavior must follow
the original material rather than being guessed from the file extension.

The original-assets mode must work without an external HD pack. If an enhanced
menu pack is selected, match its actual atlas metrics/UVs before deriving an HD
label; otherwise use the verified original-pixel version. Missing optional art
must not remove the Settings entry or hide normal navigation. Derived original
font pixels stay private/build-local; public releases should contain the
converter/recipe rather than original atlas artwork.

## Small next prototype and acceptance

1. **Offline identification only:** inspect one bounded original UI bank at a
   time (start with the 40-texture common bank and the 18-texture UI bank),
   recording archive path, texture index, native byte hash, logical/stored size
   and palette/format. Decode only selected small candidates into a private
   contact sheet, not the entire disc. Associate the visible Options item with
   its texture/UV or font draw using an existing human-supplied capture and,
   when specifically authorized, a bounded draw metadata observation.
2. **One private label prototype:** native-font rendering if proven, otherwise
   original-pixel composition. Produce normal and focused examples at the same
   logical size as a neighboring original item. Compare side by side without
   invoking the console or changing game assets. Do not claim pixel/style
   identity before that comparison.
3. **Later runtime integration:** add/extend the actual Options/pause flow with
   controller focus, back/cancel behavior, original panel/transition/sounds and
   existing settings persistence. Preserve pause/gameplay ownership, multiplayer
   rules and clear restart/resource-recreation requirements. A display-change
   confirm/revert flow is separate from label generation.

Current conclusion: the user's reuse-original-art idea is technically credible
and specific original text/font/sprite leads exist. The next safe deliverable
is one identified source resource and one private side-by-side label prototype,
not a fabricated assertion that the menu already uses the select-name font or
that a newly generated picture is identical to SC2's typography.
