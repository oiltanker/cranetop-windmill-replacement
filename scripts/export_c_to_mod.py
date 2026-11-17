"""Export Variant C from the live Blender scene to game .timbermesh files.

Run inside Blender (live bridge):  python scripts/live_client.py --file scripts/export_c_to_mod.py

Output (repo/mod/Buildings/CraneHeads/CranetopWindmill/):
  CranetopWindmill.Folktails.Model.timbermesh          finished, Folktails materials
  CranetopWindmill.IronTeeth.Model.timbermesh          finished, IronTeeth materials (D mapping)
  CranetopWindmill.{Faction}.ConstructionStage0.Model.timbermesh   base crate only

Node rig matches vanilla LargeWindTurbine so the blueprint's WindRotationAnimatorSpec
resolves #LargeBaseMIsc / #LargeRotorMIsc / #LargeShaftMIsc with vanilla axes+speeds.
"""
import math
import importlib
import os
import struct
import sys

import bpy
from mathutils import Vector

REPO = r"C:\Users\Oiltanker\Documents\Timberborn\Mods\cranetop-windmill-replacement-build"
sys.path.insert(0, os.path.join(REPO, "scripts"))
import timbermesh as tm  # noqa: E402

# The Blender process is long-lived; pick up edits to timbermesh.py on every run.
importlib.reload(tm)

COLLECTION = "Step2_VariantC"
OUT_DIR = os.path.join(REPO, "mod", "Buildings", "CraneHeads", "CranetopWindmill")

# Hitbox: BlockObjectSpec 5x5x4 (1x1 support base at the centre of layer 0 + 3 rows
# of a 5x5 pixel circle), crane attachment cell in the middle (2,2). The Blender scene
# is authored in absolute 5x5 coords (centre x/z = 2.5); to_tb's +3.5/8.0 offsets cancel
# against the pivot in extract_part (pivots carry x=0), so exported positions are
# already 5x5-anchored.
PIVOT_HEAD = Vector((0.0, 3.5, 1.090))
PIVOT_ROTOR = Vector((0.0, 3.5, 2.553))
PIVOT_SHAFT = Vector((0.0, 3.5, 0.043))
PIVOT_BASE = Vector((0.0, 3.5, 0.0))

IT_MATERIALS = {
    "BaseWood_Brown.Folktails": "BaseWood_DarkBrown.IronTeeth",
    "BaseWood_LightBrown.Folktails": "BaseWood_Grey.IronTeeth",
    "BaseWood_White.Folktails": "BaseWood_Indigo.IronTeeth",
    "BaseMetal.Folktails": "BaseMetal.IronTeeth",
    "Paper.Folktails": "BaseWood_Indigo.IronTeeth",
}


def map_material(name, faction):
    if faction == "Folktails":
        return name
    try:
        return IT_MATERIALS[name]
    except KeyError:
        raise RuntimeError(f"no IronTeeth mapping for material {name!r}")


def to_tb(p):
    """Blender world (x, y, z) -> TB (x + 3.5, z, 8 - y); the offset cancels in extract_part."""
    return Vector((p.x + 3.5, p.z, 8.0 - p.y))


def to_tb_dir(v):
    return Vector((v.x, v.z, -v.y))


def find_object(coll, prefix):
    for o in coll.objects:
        if o.type == 'MESH' and o.name.startswith(prefix):
            return o
    raise RuntimeError(f"object {prefix!r} not found in {coll.name}")


def extract_part(obj, faction, pivot_world):
    mesh = obj.data
    mesh.calc_loop_triangles()
    mw = obj.matrix_world
    rot = mw.to_3x3()
    uv_layer = mesh.uv_layers.active
    n = len(mesh.loops)

    pos = [None] * n
    nrm = [None] * n
    uvs = [None] * n
    for i, loop in enumerate(mesh.loops):
        p = mw @ mesh.vertices[loop.vertex_index].co
        pos[i] = to_tb(p) - to_tb(pivot_world)
        nrm[i] = to_tb_dir((rot @ mesh.corner_normals[i].vector).normalized()).normalized()
        uv = uv_layer.data[i].uv
        uvs[i] = (uv.x, uv.y)

    # per-loop tangents from their triangle's UV derivatives
    tang = [None] * n
    wsign = [1.0] * n
    for tri in mesh.loop_triangles:
        i0, i1, i2 = tri.loops
        p0, p1, p2 = pos[i0], pos[i1], pos[i2]
        uv0, uv1, uv2 = uvs[i0], uvs[i1], uvs[i2]
        e1, e2 = p1 - p0, p2 - p0
        duv1 = Vector((uv1[0] - uv0[0], uv1[1] - uv0[1]))
        duv2 = Vector((uv2[0] - uv0[0], uv2[1] - uv0[1]))
        det = duv1.x * duv2.y - duv2.x * duv1.y
        if abs(det) < 1e-12:
            continue
        r = 1.0 / det
        t = (e1 * duv2.y - e2 * duv1.y) * r
        b = (e2 * duv1.x - e1 * duv2.x) * r
        for li in (i0, i1, i2):
            nn = Vector(nrm[li])
            tt = t - nn * t.dot(nn)
            if tt.length < 1e-9:
                tt = Vector((1.0, 0.0, 0.0)) if abs(nn.x) < 0.9 else Vector((0.0, 1.0, 0.0))
                tt = tt - nn * tt.dot(nn)
            tang[li] = tt.normalized()
            wsign[li] = 1.0 if nn.cross(tt).dot(b) >= 0.0 else -1.0

    for i in range(n):
        if tang[i] is None:
            nn = Vector(nrm[i])
            tt = Vector((1.0, 0.0, 0.0)) if abs(nn.x) < 0.9 else Vector((0.0, 1.0, 0.0))
            tang[i] = (tt - nn * tt.dot(nn)).normalized()
            wsign[i] = 1.0

    groups = {}
    for tri in mesh.loop_triangles:
        slot = mesh.polygons[tri.polygon_index].material_index
        mat = obj.material_slots[slot].material
        mname = map_material(mat.name if mat else "BaseWood_Brown.Folktails", faction)
        groups.setdefault(mname, []).extend(tri.loops)

    props = [
        tm.VertexProperty("position", 4, 3, b"".join(struct.pack("<3f", *p) for p in pos)),
        tm.VertexProperty("normal", 4, 3, b"".join(struct.pack("<3f", *v) for v in nrm)),
        tm.VertexProperty("tangent", 4, 4, b"".join(struct.pack("<4f", t.x, t.y, t.z, w)
                                                     for t, w in zip(tang, wsign))),
        tm.VertexProperty("color", 4, 4, struct.pack("<4f", 1.0, 1.0, 1.0, 1.0) * n),
        tm.VertexProperty("uv0", 4, 2, b"".join(struct.pack("<2f", *uv) for uv in uvs)),
    ]
    submeshes = [tm.Submesh(indices, m) for m, indices in sorted(groups.items())]
    return n, props, submeshes


def make_node(name, parent, pos, data):
    count, props, submeshes = data
    return tm.Node(parent, name, tuple(pos), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0),
                   count, props, submeshes)


def node_pos(world_pivot):
    return to_tb(world_pivot)


def build_finished(coll, parts, faction):
    head = extract_part(parts["head"], faction, PIVOT_HEAD)
    rotor = extract_part(parts["rotor"], faction, PIVOT_ROTOR)
    shaft = extract_part(parts["shaft"], faction, PIVOT_SHAFT)
    body = extract_part(parts["body"], faction, PIVOT_BASE)
    crate = extract_part(parts["crate"], faction, PIVOT_BASE)

    nodes = [
        make_node("LargeWindmill.Folktails", -1, node_pos(PIVOT_BASE), body),
        make_node("CranetopBaseFrame", -1, node_pos(PIVOT_BASE), crate),
        make_node("#LargeBaseMIsc", -1, node_pos(PIVOT_HEAD), head),
        make_node("#LargeRotorMIsc", 2,
                  node_pos(PIVOT_ROTOR) - node_pos(PIVOT_HEAD), rotor),
        make_node("#LargeShaftMIsc", 2,
                  node_pos(PIVOT_SHAFT) - node_pos(PIVOT_HEAD), shaft),
    ]
    return tm.Model(name="", version=0, nodes=nodes)


def build_stage0(coll, parts, faction):
    crate = extract_part(parts["crate"], faction, PIVOT_BASE)
    return tm.Model(name="", version=0,
                    nodes=[make_node("ConstructionStage0", -1, node_pos(PIVOT_BASE), crate)])


def write_model(model, path):
    raw = tm.serialize(model)
    with open(path, "wb") as f:
        f.write(raw)
    print(f"wrote {os.path.basename(path)} ({len(raw)} B)")
    for nd in model.nodes:
        tris = sum(len(s.indices) // 3 for s in nd.submeshes)
        print(f"   {nd.name!r} parent={nd.parent} verts={nd.vertex_count} tris={tris} "
              f"pos={tuple(round(v, 3) for v in nd.position)} "
              f"mats={[s.material for s in nd.submeshes]}")


def main():
    coll = bpy.data.collections[COLLECTION]
    parts = {
        "body": find_object(coll, "LargeWindmill.Folktails"),
        "crate": find_object(coll, "CranetopBaseFrame"),
        "head": find_object(coll, "#LargeBaseMIsc"),
        "rotor": find_object(coll, "#LargeRotorMIsc"),
        "shaft": find_object(coll, "#LargeShaftMIsc"),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    for faction in ("Folktails", "IronTeeth"):
        write_model(build_finished(coll, parts, faction),
                    os.path.join(OUT_DIR, f"CranetopWindmill.{faction}.Model.timbermesh"))
        write_model(build_stage0(coll, parts, faction),
                    os.path.join(OUT_DIR,
                                 f"CranetopWindmill.{faction}.ConstructionStage0.Model.timbermesh"))
    print("export done")


main()
