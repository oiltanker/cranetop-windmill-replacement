"""Timberborn .timbermesh codec: parse, inspect, export to OBJ.

Schema verified against the game's own DTO (Timberborn.TimbermeshDTO) and
byte-exact roundtrip against CraneHeads models:

  file    = zlib stream (2-byte header + deflate) of protobuf `Model`
  Model   { 1:int Version, 2:string Name, 3:repeated Node Nodes }
  Node    { 1:int Parent (-1 = root), 2:string Name,
            3:Vector3 Position, 4:Quaternion Rotation, 5:Vector3 Scale,
            6:int VertexCount, 7:repeated VertexProperty,
            8:repeated Mesh Meshes, 9:repeated VertexAnimation,
            10:repeated NodeAnimation }
  Vector3    { 1:float X, 2:float Y, 3:float Z }
  Quaternion { 1:float X, 2:float Y, 3:float Z, 4:float W }
  VertexProperty { 1:string Name, 2:ScalarType ScalarType, 3:int Dimension,
                   4:bytes Data }        # Data little-endian, dimension*size per vertex
  Mesh    { 1:repeated int Indices, 2:string Material }   # triangle list, node-local
  ScalarType: 0 Unspecified, 1 UnsignedByte, 2 UnsignedInt, 3 Int, 4 Float, 5 Double

Node transforms are real: the importer creates one GameObject per node with
localPosition/Rotation/Scale and parents it to Nodes[Parent]. Vertices are in
node-local space, so world geometry = parent chain * TRS * v.
"""
from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass, field

# ---------------------------------------------------------------- protobuf io

def _varint(b: bytes, i: int) -> tuple[int, int]:
    r = 0
    s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        s += 7
        if not x & 0x80:
            return r, i


def _encode_varint(v: int) -> bytes:
    out = bytearray()
    while True:
        x = v & 0x7F
        v >>= 7
        if v:
            out.append(x | 0x80)
        else:
            out.append(x)
            return bytes(out)


def _tag(field_no: int, wire: int) -> bytes:
    return _encode_varint((field_no << 3) | wire)


def _len_field(field_no: int, payload: bytes) -> bytes:
    return _tag(field_no, 2) + _encode_varint(len(payload)) + payload


def _int_field(field_no: int, value: int) -> bytes:
    return _tag(field_no, 0) + _encode_varint(value & 0xFFFFFFFFFFFFFFFF)


def _fields(b: bytes):
    i = 0
    while i < len(b):
        key, i = _varint(b, i)
        f, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
            yield f, wt, v
        elif wt == 2:
            ln, i = _varint(b, i)
            yield f, wt, b[i:i + ln]
            i += ln
        elif wt in (1, 5):
            n = 8 if wt == 1 else 4
            yield f, wt, b[i:i + n]
            i += n
        else:
            raise ValueError(f"unsupported wire type {wt} at field {f}")


def _floats(b: bytes) -> dict[int, float]:
    """Parse a Vector3/Quaternion message: field n -> float32 (wire type 5)."""
    out: dict[int, float] = {}
    i = 0
    while i < len(b):
        f, wt, v = next(_fields_from(b, i))
        if wt != 5:
            raise ValueError(f"expected float32, got wire {wt} for field {f}")
        out[f] = struct.unpack("<f", v)[0]
        i += 1 + 4
    return out


def _fields_from(b: bytes, start: int):
    """Yield a single field starting at `start` (helper for sequential float parsing)."""
    key, i = _varint(b, start)
    f, wt = key >> 3, key & 7
    if wt == 0:
        v, i = _varint(b, i)
        yield f, wt, v
    elif wt == 2:
        ln, i = _varint(b, i)
        yield f, wt, b[i:i + ln]
    elif wt == 5:
        yield f, wt, b[i:i + 4]
    elif wt == 1:
        yield f, wt, b[i:i + 8]


def vec3(b: bytes) -> tuple[float, float, float]:
    d = _floats(b)
    return (d.get(1, 0.0), d.get(2, 0.0), d.get(3, 0.0))


def quat(b: bytes) -> tuple[float, float, float, float]:
    d = _floats(b)
    return (d.get(1, 0.0), d.get(2, 0.0), d.get(3, 0.0), d.get(4, 1.0))


def pack_vec3(v: tuple[float, float, float]) -> bytes:
    return b"".join(
        bytes([tag]) + struct.pack("<f", value)
        for tag, value in zip((0x0D, 0x15, 0x1D), v)
    )


def pack_quat(q: tuple[float, float, float, float]) -> bytes:
    return b"".join(
        bytes([tag]) + struct.pack("<f", value)
        for tag, value in zip((0x0D, 0x15, 0x1D, 0x25), q)
    )


# ---------------------------------------------------------------------- model

@dataclass
class VertexProperty:
    name: str
    scalar_type: int
    dimension: int
    data: bytes

    @property
    def values(self) -> list[tuple[float, ...]]:
        if self.scalar_type == 4:
            fmt, size = "f", 4
        elif self.scalar_type == 5:
            fmt, size = "d", 8
        else:
            size = 1 if self.scalar_type == 1 else 4
            fmt = "B" if self.scalar_type == 1 else "I"
        n = len(self.data) // size
        flat = struct.unpack(f"<{n}{fmt}", self.data)
        d = self.dimension
        return [tuple(flat[i:i + d]) for i in range(0, n, d)]


@dataclass
class Submesh:
    indices: list[int]
    material: str


@dataclass
class Node:
    parent: int
    name: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    scale: tuple[float, float, float]
    vertex_count: int
    properties: list[VertexProperty] = field(default_factory=list)
    submeshes: list[Submesh] = field(default_factory=list)
    raw_p: bytes | None = None
    raw_r: bytes | None = None
    raw_s: bytes | None = None

    def prop(self, name: str) -> VertexProperty | None:
        return next((p for p in self.properties if p.name == name), None)

    def world_matrix(self, model: "Model") -> "Mat4":
        m = trs(self.position, self.rotation, self.scale)
        n = self
        guard = 0
        while n.parent >= 0 and guard < 64:
            n = model.nodes[n.parent]
            m = mat_mul(trs(n.position, n.rotation, n.scale), m)
            guard += 1
        return m


@dataclass
class Model:
    name: str
    version: int = 0
    nodes: list[Node] = field(default_factory=list)

    def node(self, name: str) -> Node | None:
        return next((n for n in self.nodes if n.name == name), None)


# ------------------------------------------------------- transforms (4x4 row)

Mat4 = tuple[tuple[float, float, float, float], ...]


def trs(p, q, s) -> Mat4:
    x, y, z, w = q
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    r = (
        (1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)),
        (2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)),
        (2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)),
    )
    return (
        (r[0][0] * s[0], r[0][1] * s[1], r[0][2] * s[2], p[0]),
        (r[1][0] * s[0], r[1][1] * s[1], r[1][2] * s[2], p[1]),
        (r[2][0] * s[0], r[2][1] * s[1], r[2][2] * s[2], p[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


def mat_mul(a: Mat4, b: Mat4) -> Mat4:
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4))
        for i in range(4)
    )


def apply_point(m: Mat4, v) -> tuple[float, float, float]:
    x, y, z = v
    return (
        m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
        m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
        m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3],
    )


def apply_dir(m: Mat4, v) -> tuple[float, float, float]:
    x, y, z = v
    return (
        m[0][0] * x + m[0][1] * y + m[0][2] * z,
        m[1][0] * x + m[1][1] * y + m[1][2] * z,
        m[2][0] * x + m[2][1] * y + m[2][2] * z,
    )


# ---------------------------------------------------------------------- codec

def parse(raw: bytes) -> Model:
    data = zlib.decompress(raw)
    model = Model(name="")
    for f, wt, v in _fields(data):
        if f == 1:
            model.version = v
        elif f == 2:
            model.name = v.decode()
        elif f == 3:
            model.nodes.append(_parse_node(v))
    return model


def _parse_node(b: bytes) -> Node:
    parent = -1
    name = ""
    pos = (0.0, 0.0, 0.0)
    rot = (0.0, 0.0, 0.0, 1.0)
    scale = (1.0, 1.0, 1.0)
    count = 0
    props: list[VertexProperty] = []
    subs: list[Submesh] = []
    raw = {}
    for f, wt, v in _fields(b):
        if f == 1:
            parent = v - (1 << 64) if v >= (1 << 63) else v
        elif f == 2:
            name = v.decode()
        elif f == 3:
            pos = vec3(v)
            raw["raw_p"] = v
        elif f == 4:
            rot = quat(v)
            raw["raw_r"] = v
        elif f == 5:
            scale = vec3(v)
            raw["raw_s"] = v
        elif f == 6:
            count = v
        elif f == 7:
            props.append(_parse_prop(v))
        elif f == 8:
            subs.append(_parse_submesh(v))
    return Node(parent, name, pos, rot, scale, count, props, subs, **raw)


def _parse_prop(b: bytes) -> VertexProperty:
    name = ""
    stype = 0
    dim = 0
    data = b""
    for f, wt, v in _fields(b):
        if f == 1:
            name = v.decode()
        elif f == 2:
            stype = v
        elif f == 3:
            dim = v
        elif f == 4:
            data = v
    return VertexProperty(name, stype, dim, data)


def _parse_submesh(b: bytes) -> Submesh:
    idx: list[int] = []
    mat = ""
    for f, wt, v in _fields(b):
        if f == 1:
            if wt == 0:
                idx.append(v)
            else:  # packed repeated int
                i = 0
                while i < len(v):
                    n, i = _varint(v, i)
                    idx.append(n)
        elif f == 2:
            mat = v.decode()
    return Submesh(idx, mat)


# The game's TimbermeshReader hard-requires the zlib header bytes 0x78 0x9C
# (FirstZLibHeaderByte = 120, SecondZLibHeaderByte = 156) and then reads a raw
# DeflateStream. zlib.compress(level=9) emits 0x78 0xDA and is rejected, so build
# the stream by hand: 0x78 0x9C + raw deflate + big-endian adler32(payload).
ZLIB_HEADER = b"\x78\x9c"


def serialize(model: Model) -> bytes:
    inner = b""
    if model.name:
        inner += _len_field(2, model.name.encode())
    if model.version:
        inner += _int_field(1, model.version)
    for n in model.nodes:
        inner += _len_field(3, _serialize_node(n))
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = comp.compress(inner) + comp.flush()
    return ZLIB_HEADER + body + struct.pack(">I", zlib.adler32(inner) & 0xFFFFFFFF)


def _serialize_node(n: Node) -> bytes:
    # Canonical protobuf: always write parent (game files do, even for -1), omit
    # count 0, pack repeated indices. Both packed and unpacked read fine.
    out = _int_field(1, n.parent)
    if n.name:
        out += _len_field(2, n.name.encode())
    out += _len_field(3, n.raw_p if n.raw_p is not None else pack_vec3(n.position))
    out += _len_field(4, n.raw_r if n.raw_r is not None else pack_quat(n.rotation))
    out += _len_field(5, n.raw_s if n.raw_s is not None else pack_vec3(n.scale))
    if n.vertex_count:
        out += _int_field(6, n.vertex_count)
    for p in n.properties:
        body = _len_field(1, p.name.encode())
        body += _int_field(2, p.scalar_type) + _int_field(3, p.dimension)
        body += _len_field(4, p.data)
        out += _len_field(7, body)
    for s in n.submeshes:
        body = b""
        if s.indices:
            body += _len_field(1, b"".join(_encode_varint(i) for i in s.indices))
        body += _len_field(2, s.material.encode())
        out += _len_field(8, body)
    return out


# -------------------------------------------------------------------- export

def flatten(model: Model) -> list[dict]:
    """Return nodes with world-space vertex data (transforms baked)."""
    out = []
    for n in model.nodes:
        m = n.world_matrix(model)
        pos = n.prop("position")
        if not pos:
            continue
        verts = [apply_point(m, v) for v in pos.values]
        entry = dict(name=n.name, source=n, verts=verts)
        normal = n.prop("normal")
        if normal:
            entry["normals"] = [apply_dir(m, v) for v in normal.values]
        uv = n.prop("uv0")
        if uv:
            entry["uvs"] = uv.values
        entry["submeshes"] = n.submeshes
        out.append(entry)
    return out


def to_obj(model: Model, obj_path: str, mtl_path: str) -> dict:
    parts = flatten(model)
    materials: dict[str, tuple[float, float, float]] = {}
    stats = {}
    obj_name = obj_path.replace("\\", "/").rsplit("/", 1)[-1]
    mtl_name = mtl_path.replace("\\", "/").rsplit("/", 1)[-1]
    with open(obj_path, "w", encoding="utf-8") as f:
        f.write(f"# {model.name}\nmtllib {mtl_name}\n")
        offset = 1
        for part in parts:
            verts = part["verts"]
            has_uv = "uvs" in part
            has_n = "normals" in part
            f.write(f"o {part['name']}\n")
            for x, y, z in verts:
                f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
            if has_uv:
                for u, v in part["uvs"]:
                    f.write(f"vt {u:.6f} {v:.6f}\n")
            if has_n:
                for x, y, z in part["normals"]:
                    f.write(f"vn {x:.6f} {y:.6f} {z:.6f}\n")
            for sm in part["submeshes"]:
                materials.setdefault(sm.material, _color_for(sm.material))
                f.write(f"usemtl {sm.material}\n")
                idx = sm.indices
                for t in range(0, len(idx) - 2, 3):
                    tri = (idx[t] + offset, idx[t + 1] + offset, idx[t + 2] + offset)
                    if has_uv and has_n:
                        f.write("f " + " ".join(f"{i}/{i}/{i}" for i in tri) + "\n")
                    elif has_uv:
                        f.write("f " + " ".join(f"{i}/{i}" for i in tri) + "\n")
                    elif has_n:
                        f.write("f " + " ".join(f"{i}//{i}" for i in tri) + "\n")
                    else:
                        f.write("f " + " ".join(str(i) for i in tri) + "\n")
            xs = [v[0] for v in verts]
            ys = [v[1] for v in verts]
            zs = [v[2] for v in verts]
            stats[part["name"]] = dict(
                verts=len(verts),
                tris=sum(len(s.indices) // 3 for s in part["submeshes"]),
                bbox=((round(min(xs), 3), round(min(ys), 3), round(min(zs), 3)),
                      (round(max(xs), 3), round(max(ys), 3), round(max(zs), 3))),
                materials=sorted({s.material for s in part["submeshes"]}),
            )
            offset += len(verts)
    with open(mtl_path, "w", encoding="utf-8") as f:
        for name, rgb in materials.items():
            f.write(f"newmtl {name}\nKd {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f}\n")
            f.write("Ka 0.1 0.1 0.1\nKs 0.0 0.0 0.0\nd 1.0\nillum 1\n\n")
    return stats


def _color_for(material: str) -> tuple[float, float, float]:
    s = material.lower()
    if "metal" in s:
        return (0.55, 0.57, 0.60)
    if "indigo" in s:
        return (0.25, 0.25, 0.55)
    if "grey" in s:
        return (0.55, 0.55, 0.55)
    if "white" in s:
        return (0.88, 0.86, 0.80)
    if "paper" in s:
        return (0.82, 0.78, 0.62)
    if "lightbrown" in s:
        return (0.62, 0.44, 0.24)
    if "darkbrown" in s:
        return (0.35, 0.22, 0.12)
    if "brown" in s:
        return (0.48, 0.32, 0.17)
    return (0.60, 0.45, 0.30)


def summarize(model: Model) -> str:
    lines = [f"model: {model.name}  version={model.version}  nodes={len(model.nodes)}"]
    for i, n in enumerate(model.nodes):
        tris = sum(len(s.indices) // 3 for s in n.submeshes)
        lines.append(
            f"  [{i}] {n.name!r} parent={n.parent} verts={n.vertex_count} tris={tris}\n"
            f"      pos={tuple(round(v, 3) for v in n.position)} "
            f"rot={tuple(round(v, 3) for v in n.rotation)} "
            f"scale={tuple(round(v, 3) for v in n.scale)}\n"
            f"      props={[(p.name, p.scalar_type, p.dimension) for p in n.properties]}\n"
            f"      mats={sorted({s.material for s in n.submeshes})}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Inspect/convert .timbermesh")
    ap.add_argument("path")
    ap.add_argument("--obj", help="write OBJ (+MTL) to this path")
    ap.add_argument("--json", help="write node summary JSON")
    ap.add_argument("--roundtrip", action="store_true", help="re-serialize and compare")
    args = ap.parse_args()

    raw = open(args.path, "rb").read()
    model = parse(raw)
    print(summarize(model))
    if args.roundtrip:
        again = serialize(model)
        ok_payload = zlib.decompress(again) == zlib.decompress(raw)
        print("payload roundtrip:", "IDENTICAL" if ok_payload else "DIFFERS")
        print("semantic:", "IDENTICAL" if summarize(parse(again)) == summarize(model) else "DIFFERS")
    if args.obj:
        mtl = args.obj.rsplit(".", 1)[0] + ".mtl"
        stats = to_obj(model, args.obj, mtl)
        for name, s in stats.items():
            print(f"  obj {name}: verts={s['verts']} tris={s['tris']} bbox={s['bbox']}")
        print("wrote", args.obj, mtl)
    if args.json:
        data = [
            dict(name=n.name, parent=n.parent, position=n.position, rotation=n.rotation,
                 scale=n.scale, vertex_count=n.vertex_count,
                 properties=[dict(name=p.name, scalar_type=p.scalar_type,
                                  dimension=p.dimension) for p in n.properties],
                 materials=sorted({s.material for s in n.submeshes}))
            for n in model.nodes
        ]
        open(args.json, "w", encoding="utf-8").write(json.dumps(
            dict(name=model.name, version=model.version, nodes=data), indent=2))
        print("wrote", args.json)
