"""Static validation of the replacement mod: models + merged blueprints."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import timbermesh as tm

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(REPO, "mod")
MODEL_DIR = os.path.join(MOD, "Buildings", "CraneHeads", "CranetopWindmill")
CRANE_MOD = (r"C:\Program Files (x86)\Steam\steamapps\workshop\content\1062090"
             r"\3794340830\version-1.1")
VANILLA_BP = os.path.join(os.environ["TEMP"], "kilo", "vanilla_blueprints",
                          "Buildings", "Power", "LargeWindTurbine",
                          "LargeWindTurbine.Folktails.blueprint.json")

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        failures.append(msg)


def merge(base, patch):
    if not isinstance(base, dict) or not isinstance(patch, dict):
        return patch
    out = dict(base)
    for k, v in patch.items():
        out[k] = merge(out[k], v) if k in out else v
    return out


def bbox(model):
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for part in tm.flatten(model):
        for v in part["verts"]:
            for i in range(3):
                lo[i] = min(lo[i], v[i])
                hi[i] = max(hi[i], v[i])
    return tuple(round(v, 3) for v in lo), tuple(round(v, 3) for v in hi)


def part_bboxes(model):
    out = {}
    for part in tm.flatten(model):
        pts = part["verts"]
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
        out[part["name"]] = lo + hi
    return out


def relative(bb, cx, cz):
    """Bbox relative to the building cell centre (x, z)."""
    return [bb[0] - cx, bb[1], bb[2] - cz, bb[3] - cx, bb[4], bb[5] - cz]


def check_orientation(model, vanilla_parts):
    """Guard the Blender Y-up -> Timberborn Z mapping (front = -Z, tail = +Z)."""
    parts = part_bboxes(model)
    print(f"  orientation (relative to cell centre):")
    for name in ("#LargeBaseMIsc", "#LargeShaftMIsc"):
        ours = relative(parts[name], 2.5, 2.5)
        ref = relative(vanilla_parts[name], 1.5, 1.5)
        print(f"    {name} ours={[round(v, 3) for v in ours]} vanilla={[round(v, 3) for v in ref]}")
        check(all(abs(ours[i] - ref[i]) < 0.02 for i in (0, 2, 3, 5)),
              f"{name} matches vanilla x/z orientation (y differs with body height)")
    rotor = relative(parts["#LargeRotorMIsc"], 2.5, 2.5)
    ref = relative(vanilla_parts["#LargeRotorMIsc"], 1.5, 1.5)
    print(f"    #LargeRotorMIsc ours={[round(v, 3) for v in rotor]} vanilla={[round(v, 3) for v in ref]}")
    check(abs(rotor[2] - ref[2]) < 0.02, "rotor front plane on -Z side (no Y/Z flip)")
    check(abs((rotor[3] - rotor[0]) / (ref[3] - ref[0]) - 1.25) < 0.03,
          "rotor diameter scaled 1.25x (width)")


def validate_model(path, expected_names, expected_bbox, parent_map, vanilla_parts=None):
    print(f"\nMODEL {os.path.basename(path)}")
    raw = open(path, "rb").read()
    check(raw[:2] == b"\x78\x9c", f"zlib header 789c (got {raw[:2].hex(' ')})")
    model = tm.parse(raw)
    names = [n.name for n in model.nodes]
    check(names == expected_names, f"nodes {names}")
    check(tm.serialize(model) is not None, "serializes")
    check(tm.parse(tm.serialize(model)).name == model.name, "roundtrip")
    for i, n in enumerate(model.nodes):
        check(n.parent == parent_map[i], f"{n.name!r} parent {n.parent}")
        check(n.vertex_count == len(n.prop("position").values), f"{n.name!r} vertex_count matches")
        for p in ("position", "normal", "tangent", "color", "uv0"):
            prop = n.prop(p)
            check(prop is not None and len(prop.values) == n.vertex_count,
                  f"{n.name!r} prop {p}")
        check(len({s.material for s in n.submeshes}) == len(n.submeshes),
              f"{n.name!r} submeshes unique materials")
        idx = max((max(s.indices) for s in n.submeshes), default=-1)
        check(idx < n.vertex_count, f"{n.name!r} indices in range")
    lo, hi = bbox(model)
    print(f"  bbox {lo} .. {hi}")
    check(all(abs(a - b) < 0.02 for a, b in zip(lo, expected_bbox[0])), "bbox min")
    check(all(abs(a - b) < 0.02 for a, b in zip(hi, expected_bbox[1])), "bbox max")
    if vanilla_parts is not None:
        check_orientation(model, vanilla_parts)
    return model


def main():
    mats = {"BaseWood_Brown.Folktails", "BaseWood_LightBrown.Folktails",
            "BaseWood_White.Folktails", "BaseMetal.Folktails", "Paper.Folktails",
            "BaseWood_DarkBrown.IronTeeth", "BaseWood_Grey.IronTeeth",
            "BaseWood_Indigo.IronTeeth"}
    print("MATERIALS known:", len(mats))

    finished_names = ["LargeWindmill.Folktails", "CranetopBaseFrame",
                      "#LargeBaseMIsc", "#LargeRotorMIsc", "#LargeShaftMIsc"]
    parents = [-1, -1, -1, 2, 2]
    vanilla_mesh = os.path.join(REPO, "models", "vanilla_large_turbine.timbermesh")
    vanilla_parts = None
    if os.path.exists(vanilla_mesh):
        vanilla_parts = part_bboxes(tm.parse(open(vanilla_mesh, "rb").read()))
    else:
        print("  NOTE: vanilla turbine mesh absent - skipping orientation check")
    for faction in ("Folktails", "IronTeeth"):
        model = validate_model(
            os.path.join(MODEL_DIR, f"CranetopWindmill.{faction}.Model.timbermesh"),
            finished_names, ((0.95, 0.0, 1.52), (4.05, 4.10, 3.97)), parents,
            vanilla_parts)
        found = {s.material for n in model.nodes for s in n.submeshes}
        print(f"  materials {sorted(found)}")
        check(all(m in mats for m in found), "all materials known")
        check(all(m.endswith("." + faction) for m in found), "material faction suffix")
        heads = [n for n in model.nodes if n.name in ("#LargeBaseMIsc", "#LargeRotorMIsc", "#LargeShaftMIsc")]
        check([n.name for n in heads] == ["#LargeBaseMIsc", "#LargeRotorMIsc", "#LargeShaftMIsc"],
              "animator node names present")
        for n in heads:
            world = n.world_matrix(model)
            check(abs(world[0][3] - 2.5) < 1e-4 and abs(world[2][3] - 2.5) < 1e-4,
                  f"{n.name!r} pivot on 5x5 footprint centre axis")

        validate_model(
            os.path.join(MODEL_DIR, f"CranetopWindmill.{faction}.ConstructionStage0.Model.timbermesh"),
            ["ConstructionStage0"], ((2.0, 0.0, 2.0), (3.0, 0.14, 3.0)), [-1])

    print("\nBLUEPRINTS")
    vanilla_bp = json.load(open(VANILLA_BP, encoding="utf-8"))
    for faction in ("Folktails", "IronTeeth"):
        base_path = os.path.join(CRANE_MOD, "Buildings", "CraneHeads", "CranetopWindmill",
                                 f"CranetopWindmill.{faction}.blueprint.json")
        fragment_path = os.path.join(MODEL_DIR, f"CranetopWindmill.{faction}.blueprint.json")
        base = json.load(open(base_path, encoding="utf-8-sig"))
        frag = json.load(open(fragment_path))
        merged = merge(base, frag)
        print(f"\n  {faction}: model={merged['Children']['#Finished']['TimbermeshSpec']['Model']}")
        spec = merged["WindRotationAnimatorSpec"]
        model = tm.parse(open(os.path.join(
            MODEL_DIR, f"CranetopWindmill.{faction}.Model.timbermesh"), "rb").read())
        names = {n.name for n in model.nodes}
        for r in spec["WindRotators"]:
            check(r["TransformName"] in names, f"rotator {r['TransformName']}")
            check(sum(abs(v) for v in r["RotationAxis"].values()) == 1.0, "axis unit")
        check(spec["Tower"]["TransformName"] in names, "tower transform")
        check(spec["Tower"]["RotationSpeed"] == 80.0, "tower speed 80")
        cost = merged["BuildingSpec"]["BuildingCost"]
        print(f"  cost {cost}")
        check(not any(c["Id"] == "Paper" for c in cost), "no Paper cost")
        check(merged["TemplateSpec"]["TemplateName"] == f"CranetopWindmill.{faction}", "template name")
        block = merged["BlockObjectSpec"]
        print(f"  block size {block['Size']} blocks={len(block['Blocks'])}")
        check(block["Size"] == {"X": 5, "Y": 5, "Z": 5},
              "hitbox footprint 5x5, height 5 (BlockObjectSpec: X/Y horizontal, Z vertical)")
        check(len(block["Blocks"]) == 125, "125 occupancy cells")

        def layer(y):
            base = 25 * y
            return [(i % 5, (i // 5) % 5) for i in range(base, base + 25)
                    if block["Blocks"][i]["Occupations"] != "None"]

        base_cells = layer(0)
        check(base_cells == [(2, 2)], f"base layer 1x1 support cell {base_cells}")
        check(block["Blocks"][2 + 5 * 2]["MatterBelow"] == "Stackable",
              "base cell requires stackable below (crane tower; original head + Jib convention)")

        def layer(y):
            base = 25 * y
            return [(i % 5, (i // 5) % 5) for i in range(base, base + 25)
                    if block["Blocks"][i]["Occupations"] != "None"]

        base_cells = layer(0)
        check(base_cells == [(2, 2)], f"base layer 1x1 support cell {base_cells}")
        circle = {(1, 0), (2, 0), (3, 0)}
        circle |= {(x, z) for z in range(1, 4) for x in range(5)}
        circle |= {(1, 4), (2, 4), (3, 4)}
        cap = {(x, z) for z in range(1, 4) for x in range(1, 4)}
        for z in (1, 2):
            cells = layer(z)
            check(len(cells) == 21 and set(cells) == circle,
                  f"layer {z} 5x5 pixel circle (21 cells)")
            check(all(block["Blocks"][x + 5 * (y + 5 * z)]["Occupations"] == "All"
                      for x, y in cells), f"layer {z} cells block all occupations")
        top = layer(3)
        check(len(top) == 21 and set(top) == circle, "z=3 layer 5x5 pixel circle (21 cells)")
        check(all(block["Blocks"][x + 5 * (y + 5 * 3)]["Occupations"]
                  == "Floor, Bottom, Corners, Path, Middle" for x, y in top),
              "z=3 layer walkable Floor (vanilla turbine top convention)")
        cap_l = layer(4)
        check(len(cap_l) == 9 and set(cap_l) == cap,
              "z=4 cap 3x3 centred at (2,2)")
        cap_idx = {x + 5 * y + 100 for x, y in cap
                   if block["Blocks"][x + 5 * y + 100]["Occupations"] != "None"}
        check(cap_idx == {106, 107, 108, 111, 112, 113, 116, 117, 118},
              "z=4 cap at indices 106-108, 111-113, 116-118")
        check(all(block["Blocks"][i]["Occupations"]
                  == "Floor, Bottom, Corners, Path, Middle"
                   for i in cap_idx), "z=4 cap walkable Floor")
        attach = merged["CraneHeadSpec"]["AttachmentCoordinates"]
        check(attach == {"X": 2, "Y": 2, "Z": 0}, "attachment cell at 5x5 centre (2,2)")
        coll = merged["Children"]["#Finished"]["CollidersSpec"]
        check(coll["BoxColliders"][0]["Center"] == {"X": 2.5, "Y": 1.8, "Z": 2.5},
              "finished collider at 5x5 centre")
        nested = merged["Children"]["#Unfinished"]["Children"]["ConstructionBase1x1#nested"]
        pos = nested["Modification"]["TransformSpec"]["Position"]
        check(pos == {"X": 2.0, "Y": 0.0, "Z": 2.0}, "construction base at 5x5 centre")
        stage_coll = merged["Children"]["#Unfinished"]["Children"]["ConstructionStage0"]["CollidersSpec"]
        check(stage_coll["BoxColliders"][0]["Center"] == {"X": 2.5, "Y": 0.05, "Z": 2.5},
              "stage0 collider at 5x5 centre")
        check(merged["WindRotationAnimatorSpec"] == vanilla_bp["WindRotationAnimatorSpec"],
              "rotations == vanilla LargeWindTurbine")
        stage = merged["Children"]["#Unfinished"]["Children"]["ConstructionStage0"]["TimbermeshSpec"]["Model"]
        check(stage.endswith(".ConstructionStage0.Model"), "stage0 model override")
        check("ConstructionBase1x1#nested" in merged["Children"]["#Unfinished"]["Children"],
              "construction base kept")

    print("\nMANIFEST")
    man = json.load(open(os.path.join(MOD, "manifest.json")))
    check(man["RequiredMods"] == [{"Id": "CraneHeads"}], "requires CraneHeads")

    print("\nRESULT:", "PASS" if not failures else f"{len(failures)} FAILURES")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
