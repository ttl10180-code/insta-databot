"""오디(Odi) 3D 마스코트 렌더러 — Blender(bpy) 로 주제별 클레이 캐릭터 PNG 를 굽는다.

  python3.11 tools/build_mascot.py [주제 ...]

결과: assets/mascot/odi-<topic>.png (투명 배경, 정사각)
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "mascot"

# 주제별 팔레트: (몸통 밝은쪽, 몸통 그늘쪽, 안테나/림 발광색)
THEMES = {
    "weather":    ((0.62, 0.84, 1.00), (0.17, 0.36, 0.78), (0.23, 0.51, 0.96)),
    "air":        ((0.55, 0.95, 0.86), (0.04, 0.45, 0.42), (0.08, 0.72, 0.65)),
    "realestate": ((0.99, 0.75, 0.33), (0.55, 0.27, 0.02), (0.96, 0.62, 0.04)),
    "oil":        ((1.00, 0.59, 0.33), (0.58, 0.15, 0.05), (0.98, 0.45, 0.09)),
    "boxoffice":  ((0.80, 0.71, 1.00), (0.33, 0.12, 0.60), (0.55, 0.36, 0.96)),
    "exchange":   ((0.58, 0.90, 0.98), (0.03, 0.33, 0.45), (0.02, 0.71, 0.83)),
    "lifeindex":  ((0.83, 0.95, 0.56), (0.27, 0.42, 0.03), (0.52, 0.80, 0.09)),
    "price":      ((1.00, 0.71, 0.77), (0.53, 0.09, 0.23), (0.96, 0.25, 0.37)),
    "apply":      ((0.99, 0.82, 0.45), (0.43, 0.23, 0.03), (0.85, 0.47, 0.02)),
}

RES = 1100
SAMPLES = 96
if os.getenv("QUICK"):  # 형태만 빠르게 확인할 때
    RES, SAMPLES = 520, 20


def srgb(c):
    """sRGB 값을 Blender 의 선형 공간으로."""
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, color, *, rough=0.38, subsurf=0.0, emit=None, emit_strength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*srgb(color), 1)
    b.inputs["Roughness"].default_value = rough
    if "Subsurface Weight" in b.inputs:
        b.inputs["Subsurface Weight"].default_value = subsurf
        if subsurf:
            b.inputs["Subsurface Radius"].default_value = (0.25, 0.14, 0.10)
    if emit is not None:
        b.inputs["Emission Color"].default_value = (*srgb(emit), 1)
        b.inputs["Emission Strength"].default_value = emit_strength
    return m


def sphere(name, loc, scale, material, segs=64):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=segs // 2, radius=1.0, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.shade_smooth()
    o.data.materials.append(material)
    return o


def cone(name, loc, rot, radius, depth, material, bevel=0.05):
    bpy.ops.mesh.primitive_cone_add(vertices=64, radius1=radius, radius2=0.0,
                                    depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    m = o.modifiers.new("bevel", "BEVEL")
    m.width, m.segments, m.limit_method = bevel, 6, "ANGLE"
    bpy.ops.object.shade_smooth()
    o.data.materials.append(material)
    return o


def tube(name, points, depth, material):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for i, p in enumerate(points):
        sp.points[i].co = (*p, 1.0)
    cu.bevel_depth = depth
    cu.bevel_resolution = 8
    cu.use_fill_caps = True
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(material)
    return o


def on_body(x, z, out=0.012):
    """몸통 표면(반지름 1, y/z 눌림) 위의 y 좌표 — 살짝 바깥으로 띄운다."""
    r2 = max(0.0, 1.0 - x * x - (z / 0.90) ** 2)
    return -(0.95 * math.sqrt(r2) + out)


def build(theme: str, mood: str | None = None) -> Path:
    light, dark, glow = THEMES[theme]
    clear()
    scene = bpy.context.scene

    def clay(name: str, blush: bool):
        """클레이 몸통 머티리얼 — blush=False 면 볼터치 없이 같은 그라디언트만."""
        m = mat(name, light, rough=0.34, subsurf=0.22)
        # 몸통에 위→아래 그라디언트를 입혀 클레이 느낌의 음영을 만든다
        nt = m.node_tree
        bsdf = nt.nodes["Principled BSDF"]
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.05
        ramp.color_ramp.elements[0].color = (*srgb(light), 1)
        ramp.color_ramp.elements[1].position = 0.95
        ramp.color_ramp.elements[1].color = (*srgb(dark), 1)
        grad = nt.nodes.new("ShaderNodeTexGradient")
        grad.gradient_type = "LINEAR"
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.inputs["Rotation"].default_value = (0, math.radians(-90), 0)
        coord = nt.nodes.new("ShaderNodeTexCoord")
        nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
        nt.links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
        if not blush:
            nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
            return m

        # 볼터치: 표면 위 두 점으로부터의 거리를 마스크로 만들어 분홍색을 섞는다
        coord2 = nt.nodes.new("ShaderNodeTexCoord")
        masks = []
        for sx in (-1, 1):
            dist = nt.nodes.new("ShaderNodeVectorMath")
            dist.operation = "DISTANCE"
            dist.inputs[1].default_value = (sx * 0.60, -0.7868, -0.1444)
            nt.links.new(coord2.outputs["Object"], dist.inputs[0])
            fall = nt.nodes.new("ShaderNodeMapRange")
            fall.inputs["From Min"].default_value = 0.14
            fall.inputs["From Max"].default_value = 0.34
            fall.inputs["To Min"].default_value = 1.0
            fall.inputs["To Max"].default_value = 0.0
            fall.clamp = True
            nt.links.new(dist.outputs["Value"], fall.inputs["Value"])
            masks.append(fall.outputs["Result"])
        both = nt.nodes.new("ShaderNodeMath")
        both.operation = "MAXIMUM"
        nt.links.new(masks[0], both.inputs[0])
        nt.links.new(masks[1], both.inputs[1])
        soft = nt.nodes.new("ShaderNodeMath")
        soft.operation = "MULTIPLY"
        soft.inputs[1].default_value = 0.72
        nt.links.new(both.outputs["Value"], soft.inputs[0])

        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        m_fac = next(i for i in mix.inputs if i.name == "Factor" and i.type == "VALUE")
        m_a = next(i for i in mix.inputs if i.name == "A" and i.type == "RGBA")
        m_b = next(i for i in mix.inputs if i.name == "B" and i.type == "RGBA")
        m_out = next(o for o in mix.outputs if o.type == "RGBA")
        m_b.default_value = (*srgb((0.98, 0.58, 0.64)), 1)
        nt.links.new(soft.outputs["Value"], m_fac)
        nt.links.new(ramp.outputs["Color"], m_a)
        nt.links.new(m_out, bsdf.inputs["Base Color"])
        return m

    m_body = clay("body", True)
    m_limb = clay("limb", False)

    m_ink = mat("ink", (0.06, 0.09, 0.17), rough=0.22)
    m_pink = mat("pink", (0.97, 0.56, 0.62), rough=0.55)

    sphere("body", (0, 0, 0), (1.0, 0.95, 0.90), m_body, segs=96)
    for sx in (-1, 1):
        # 앞발 · 뒷발
        sphere("paw", (sx * 0.99, -0.10, -0.24), (0.27, 0.23, 0.21), m_limb)
        sphere("foot", (sx * 0.40, -0.16, -0.84), (0.30, 0.27, 0.14), m_limb)
        # 눈
        sphere("eye", (sx * 0.31, on_body(sx * 0.31, 0.11) + 0.04, 0.11), (0.115, 0.075, 0.125), m_ink)
        # 고양이 귀 — 바깥 귀는 몸통색, 안쪽 귀는 분홍
        cone("ear", (sx * 0.50, 0.02, 0.92), (0, math.radians(sx * 20), 0),
             0.36, 0.62, m_limb)
        cone("ear_in", (sx * 0.49, -0.16, 0.90), (0, math.radians(sx * 20), 0),
             0.19, 0.46, m_pink, bevel=0.03)
        # 수염 3가닥
        for k, (z0, dz) in enumerate(((-0.02, 0.10), (-0.10, 0.0), (-0.18, -0.09))):
            x0 = sx * 0.42
            tube(f"whisker{k}", [
                (x0, on_body(x0, z0) + 0.02, z0),
                (sx * 0.70, -0.56, z0 + dz * 0.6),
                (sx * 0.95, -0.34, z0 + dz),
            ], 0.013, m_ink)

    # 코 — 작은 삼각형
    cone("nose", (0, on_body(0, 0.00) - 0.02, -0.005), (math.radians(90), 0, 0),
         0.085, 0.07, m_pink, bevel=0.02)

    # 입 — 코 아래 ω 모양
    for sx in (-1, 1):
        mouth = []
        for i in range(13):
            t = i / 12
            x = sx * 0.19 * t
            z = -0.09 - 0.10 * math.sin(math.pi * t) - 0.02 * t
            mouth.append((x, on_body(x, z), z))
        tube("mouth", mouth, 0.026, m_ink)

    # 꼬리 — 오른쪽 뒤에서 나와 위로 말린다
    tail = []
    for i in range(36):
        t = i / 35
        a = math.radians(-162 + 222 * t)
        tail.append((1.02 + 0.40 * math.cos(a), 0.34 - 0.08 * t, -0.32 + 0.40 * math.sin(a)))
    tube("tail", tail, 0.12, m_limb)

    # ── 무드 소품 ────────────────────────────────────────────────────
    if mood == "mask":
        m_mask = mat("mask", (0.93, 0.95, 0.98), rough=0.62)
        sphere("mask", (0, on_body(0, -0.20) + 0.02, -0.21), (0.42, 0.20, 0.27), m_mask)
        for sx in (-1, 1):
            strap = []
            for i in range(14):
                t = i / 13
                x = sx * (0.38 + 0.62 * t)
                z = -0.17 + 0.16 * t
                strap.append((x, on_body(min(abs(x), 0.95) * (1 if x > 0 else -1), z) + 0.06, z))
            tube(f"strap{sx}", strap, 0.022, m_mask)

    elif mood == "umbrella":
        m_canopy = mat("canopy", glow, rough=0.42)
        m_stick = mat("stick", (0.35, 0.24, 0.16), rough=0.5)
        cone("canopy", (0.84, -0.20, 1.56), (0, math.radians(-14), 0), 0.98, 0.46,
             m_canopy, bevel=0.14)
        tube("stick", [(1.02, -0.12, -0.10), (0.94, -0.17, 0.62), (0.86, -0.20, 1.40)],
             0.028, m_stick)

    # ── 조명: 키 / 필 / 컬러 림 ──────────────────────────────────────
    def area(name, loc, rot, size, energy, color=(1, 1, 1)):
        d = bpy.data.lights.new(name, "AREA")
        d.energy, d.size, d.color = energy, size, srgb(color)
        o = bpy.data.objects.new(name, d)
        o.location, o.rotation_euler = loc, rot
        bpy.context.collection.objects.link(o)

    area("key", (-2.6, -3.4, 3.6), (math.radians(45), 0, math.radians(-36)), 5.0, 900)
    area("fill", (3.4, -2.6, 0.4), (math.radians(84), 0, math.radians(54)), 6.0, 260)
    area("rim", (1.9, 2.9, 2.2), (math.radians(-50), 0, math.radians(205)), 4.0, 1400, glow)
    area("bounce", (0, -1.4, -3.4), (math.radians(180), 0, 0), 5.0, 130)

    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 2.95
    cam = bpy.data.objects.new("cam", cam_d)
    cam.location = (0.0, -8.0, 0.22)
    cam.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / (f"odi-{theme}-{mood}.png" if mood else f"odi-{theme}.png")
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return path


if __name__ == "__main__":
    # 인자는 "테마" 또는 "테마:무드" (예: air:mask, weather:umbrella)
    for arg in (sys.argv[1:] or list(THEMES)):
        theme, _, mood = arg.partition(":")
        print("rendered", build(theme, mood or None), flush=True)
