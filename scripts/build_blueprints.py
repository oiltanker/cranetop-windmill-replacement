"""Build the same-path CranetopWindmill blueprint fragments: a 5x5 footprint,
5-tall hitbox (1x1 support base + 3 pixel-circle layers + 3x3 walkable cap),
vanilla LargeWindTurbine colliders/rotation, our model paths.

BlockObjectSpec axis convention (verified against vanilla LargeWindTurbine,
the Jib head, and the original CranetopWindmill): X/Y are the horizontal
footprint, Z is the vertical size, blocks index = x + X*y + X*Y*z.
Vanilla turbine decodes as: 1x1 support at z=0, 1x1 column at z=1, full 3x3
All at z=2..3, walkable Floor top at z=4.

Run: python scripts/build_blueprints.py
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_BP = os.path.join(REPO, "mod", "Buildings", "CraneHeads", "CranetopWindmill")
VANILLA = os.path.join(os.environ["TEMP"], "kilo", "vanilla_blueprints",
                       "Buildings", "Power", "LargeWindTurbine",
                       "LargeWindTurbine.Folktails.blueprint.json")
MODEL_BASE = "Buildings/CraneHeads/CranetopWindmill/CranetopWindmill"


SIZE = {"X": 5, "Y": 5, "Z": 5}  # X/Y = footprint, Z = height
CENTRE = 2  # attachment cell in the 5x5 footprint

EMPTY = {"MatterBelow": "Any", "Occupations": "None", "Stackable": "None",
         "OccupyAllBelow": False, "Underground": False}
SOLID = {"MatterBelow": "Any", "Occupations": "All", "Stackable": "None",
         "OccupyAllBelow": False, "Underground": False}
TOP = {"MatterBelow": "Any", "Occupations": "Floor, Bottom, Corners, Path, Middle",
       "Stackable": "None", "OccupyAllBelow": False, "Underground": False}
SUPPORT = {"MatterBelow": "Stackable",  # crane tower top, like the original head + Jib
           "Occupations": "Bottom, Top, Corners, Path, Middle",
           "Stackable": "None", "OccupyAllBelow": False, "Underground": False}


def circle_cells():
    """Pixel circle 5 in the X/Y plane: rows (y=0..4) 1, 3, 5, 3, 1 -> 21 cells.

    Per height layer (z=1..3) the occupied indices are 1-3, 5-19, 21-23
    (index = x + X*y + X*Y*z), at offsets 25 / 50 / 75.
    """
    out = set()
    for y in range(SIZE["Y"]):
        if y in (0, SIZE["Y"] - 1):
            xs = range(CENTRE - 1, CENTRE + 2)
        elif 0 < y < SIZE["Y"] - 1:
            xs = range(SIZE["X"])
        else:
            xs = range(0)
        for x in xs:
            out.add((x, y))
    return out


def cap_cells():
    """3x3 cap centred at (CENTRE, CENTRE): indices 106-108, 111-113, 116-118."""
    return {(x, y) for x in range(CENTRE - 1, CENTRE + 2)
            for y in range(CENTRE - 1, CENTRE + 2)}


def build_blocks():
    """Blocks ordered x-fastest, then Y (depth), then Z (height) — the game's decode order.

    z=0 = 1x1 support, z=1..2 = circle All, z=3 = circle walkable Floor,
    z=4 = 3x3 walkable Floor cap.
    """
    circle = circle_cells()
    cap = cap_cells()
    blocks = []
    for z in range(SIZE["Z"]):
        for y in range(SIZE["Y"]):
            for x in range(SIZE["X"]):
                if z == 0 and (x, y) == (CENTRE, CENTRE):
                    blocks.append(dict(SUPPORT))
                elif z == 1 and (x, y) in circle:
                    blocks.append(dict(SOLID))
                elif z == 2 and (x, y) in circle:
                    blocks.append(dict(SOLID))
                elif z >= 3 and (x, y) in (cap if z == 4 else circle):
                    blocks.append(dict(TOP))
                else:
                    blocks.append(dict(EMPTY))
    assert len(blocks) == SIZE["X"] * SIZE["Y"] * SIZE["Z"]
    return blocks


def main():
    vanilla = json.load(open(VANILLA, encoding="utf-8"))["WindRotationAnimatorSpec"]
    vanilla_bp = json.load(open(VANILLA, encoding="utf-8"))
    block_spec = {"Size": dict(SIZE), "Blocks": build_blocks()}
    colliders = vanilla_bp["Children"]["#Finished"]["CollidersSpec"]
    for box in colliders["BoxColliders"]:
        box["Center"]["X"] = CENTRE + 0.5
        box["Center"]["Z"] = CENTRE + 0.5
    # keep the base 1x1: split the wide collider back to a single-cell box
    colliders["BoxColliders"][0]["Size"] = {"X": 1.0, "Y": 3.6, "Z": 1.0}

    for faction in ("Folktails", "IronTeeth"):
        fragment = {
            "BlockObjectSpec": block_spec,
            "CraneHeadSpec": {
                "AttachmentCoordinates": {"X": CENTRE, "Y": CENTRE, "Z": 0}
            },
            "WindRotationAnimatorSpec": vanilla,
            "Children": {
                "#Finished": {
                    "TimbermeshSpec": {
                        "Model": f"{MODEL_BASE}.{faction}.Model"
                    },
                    "CollidersSpec": colliders,
                },
                "#Unfinished": {
                    "Children": {
                        "ConstructionBase1x1#nested": {
                            "Modification": {
                                "TransformSpec": {
                                    "Position": {"X": float(CENTRE), "Y": 0.0, "Z": float(CENTRE)},
                                    "Rotation": {"X": 0.0, "Y": 0.0, "Z": 0.0},
                                    "Scale": {"X": 1.0, "Y": 1.0, "Z": 1.0},
                                }
                            }
                        },
                        "ConstructionStage0": {
                            "TimbermeshSpec": {
                                "Model": f"{MODEL_BASE}.{faction}.ConstructionStage0.Model"
                            },
                            "CollidersSpec": {
                                "BoxColliders": [
                                    {"Center": {"X": CENTRE + 0.5, "Y": 0.05, "Z": CENTRE + 0.5},
                                     "Size": {"X": 1.0, "Y": 0.1, "Z": 1.0}}
                                ],
                                "SphereColliders": [],
                                "CapsuleColliders": [],
                            },
                        },
                    }
                },
            },
        }
        out = os.path.join(MOD_BP, f"CranetopWindmill.{faction}.blueprint.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(fragment, f, indent=2)
            f.write("\n")
        print("wrote", os.path.basename(out))


if __name__ == "__main__":
    main()
