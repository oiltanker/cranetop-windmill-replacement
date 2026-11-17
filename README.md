# Cranetop Windmill Replacement

A Timberborn mod that replaces the **Cranetop Windmill** head from the [Crane Heads](https://steamcommunity.com/workshop/filedetails/?id=3794340830) mod with a brand-new windmill, built from the vanilla **Large Wind Turbine** parts and animated exactly like it.

## What it does

- Replaces the CranetopWindmill crane head — the little weathervane-style pinwheel on top of cranes — with a proper windmill: a timber tower with a trim collar, a large rotor and a spinning shaft.
- The rotor, the shaft and the whole head yaw with the wind at the vanilla Large Wind Turbine's speeds (rotor 80°/s, shaft −80°/s, tower 80°/s), instead of the original toy weathervane spin.
- Rotor is 1.25× the vanilla Large Wind Turbine's diameter.
- Both factions supported with per-faction materials (Iron Teeth get their own wood and indigo palette).
- Builds over the crane tower like the original head: crate first, then the finished windmill.

## What stays the same

- Same building, same template name — the mod overrides the original blueprint in place, so existing saves with placed windmill heads keep working.
- Same cost: 40 Planks, 20 Gears, 10 Metal Blocks (Science 1400).
- Same windmill bonus behavior (0.1 bonus per section, same minimum wind strength).
- Still attaches to crane towers and rebuilds with them, exactly like the original head.

## New size

- Footprint 5×5 blocks, 5 blocks tall (the original was 1×1×2).
- A 1×1 support cell sits on the crane tower top; the body occupies a circular 5×5 area.
- The top of the tower and a 3×3 platform at the very top are walkable.

## Requirements

- [Crane Heads] mod (which requires [Crane] and [ModdableToolGroups]).
- Timberborn 1.1.1 or newer.

## Compatibility

- Save-safe: adding or removing the mod does not corrupt saves. Heads placed with the original Crane Heads windmill keep their template after the swap.
- The override is a same-path blueprint fragment; if a user-set mod priority loads this mod *before* Crane Heads, the original weathervane would win — keep this mod after Crane Heads in the load order.

## Build

Copies `mod/` into your local Timberborn mods folder:

```
python build.py
```

Optional flags: `--mods-dir DIR` (override the mods directory; auto-detected from the user profile on Windows, including the Proton prefix on SteamOS/Linux) and `--folder-name NAME` (default `cranetop-windmill-replacement-mod`).
