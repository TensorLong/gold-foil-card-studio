"""Blender 4.5+: build an editable reflection-swept gold-line card from two PNGs."""
import argparse
from array import array
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a number')
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be finite, in [{low}, {high}]')
    return value


def configuration(project):
    cfg = json.loads((project / 'card-config.json').read_text(encoding='utf-8-sig'))
    gold = cfg.get('gold', {})
    defaults = {'emission': (8, 0, 40), 'phase': (0, -100, 100),
                'repeat': (6, .01, 40), 'noiseScale': (600, 1, 4000),
                'noiseAmount': (-.2, -2, 2), 'sweepBlack': (.5, 0, 1),
                'sweepWhite': (.82, 0, 1), 'lineBlack': (.08, 0, 1),
                'lineWhite': (.35, 0, 1)}
    params = {key: number(gold.get(key, default), key, low, high)
              for key, (default, low, high) in defaults.items()}
    for key, default, low, high in [('color', [1, .72, .22], 0, 1),
                                   ('mappingRotation', [0, 0, 32], -360, 360)]:
        values = gold.get(key, default)
        if not isinstance(values, list) or len(values) != 3:
            raise ValueError(f'{key} requires three numbers')
        params[key] = [number(v, key, low, high) for v in values]
    for key in ('sweep', 'line'):
        if params[key + 'Black'] >= params[key + 'White']:
            raise ValueError(f'{key}Black must be below {key}White')
    palette = cfg.get('printPalette')
    if palette is not None:
        if not isinstance(palette, dict):
            raise ValueError('printPalette must contain ink and stock linear RGB')
        params['printPalette'] = {}
        for role in ('ink', 'stock'):
            values = palette.get(role)
            if not isinstance(values, list) or len(values) != 3:
                raise ValueError(f'printPalette.{role} requires three numbers')
            params['printPalette'][role] = [number(v, role, 0, 1) for v in values]
    render = cfg.get('render', {})
    width = number(render.get('width', 720), 'width', 128, 4096)
    samples = number(render.get('samples', 32), 'samples', 1, 1024)
    if int(width) != width or int(samples) != samples:
        raise ValueError('width and samples must be integers')
    paths = {}
    for role in ('artwork', 'lineart'):
        value = cfg.get('assets', {}).get(role, f'assets/{role}.png')
        if not isinstance(value, str) or Path(value).is_absolute():
            raise ValueError(f'{role}: use a project-relative PNG path')
        path = (project / value).resolve()
        if not path.is_relative_to(project) or path.suffix.lower() != '.png':
            raise ValueError(f'{role}: PNG must remain inside the project')
        if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError(f'{role}: missing PNG or larger than 32 MiB')
        # Check dimensions before decoding an untrusted raster.
        with path.open('rb') as file:
            header = file.read(24)
        if header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
            raise ValueError(f'{role}: invalid PNG header')
        w, h = int.from_bytes(header[16:20], 'big'), int.from_bytes(header[20:24], 'big')
        if not (1 <= w <= 8192 and 1 <= h <= 8192 and w * h <= 16_777_216):
            raise ValueError(f'{role}: invalid dimensions or more than 16 MP')
        paths[role] = path
    return cfg, params, paths, int(width), int(samples)


def node(tree, kind, name, x, y):
    n = tree.nodes.new(kind)
    n.name = n.label = name
    n.location = (x, y)
    return n


def connect(tree, source, output, target, input_name):
    tree.links.new(source.outputs[output], target.inputs[input_name])


def math_node(tree, operation, name, x, y, second=0):
    n = node(tree, 'ShaderNodeMath', name, x, y)
    n.operation = operation
    n.inputs[1].default_value = second
    return n


def ramp(tree, name, x, y, low, high, invert=False):
    n = node(tree, 'ShaderNodeValToRGB', name, x, y)
    n.color_ramp.interpolation = 'LINEAR'
    for element, position, value in zip(n.color_ramp.elements, [low, high],
                                        [1, 0] if invert else [0, 1]):
        element.position = position
        element.color = (value, value, value, 1)
    return n


def material(images, p):
    mat = bpy.data.materials.new('Gold Foil Card / Printed Art + Gold Lines')
    mat.use_nodes = True
    t = mat.node_tree
    t.nodes.clear()
    uv = node(t, 'ShaderNodeTexCoord', 'Image UV', -800, 0)
    textures = {}
    for index, role in enumerate(('artwork', 'lineart')):
        tex = node(t, 'ShaderNodeTexImage', role, -560, 100 - index * 360)
        tex.image = images[role]
        tex.extension = 'EXTEND'
        connect(t, uv, 'UV', tex, 'Vector')
        textures[role] = tex
    printed = node(t, 'ShaderNodeBsdfPrincipled', 'Printed Artwork', -200, 150)
    printed.inputs['Metallic'].default_value = 0
    printed.inputs['Roughness'].default_value = .7
    if 'printPalette' in p:
        palette = ramp(t, 'Full Gold / Registered Master Palette', -320, 450, 0, 1)
        for element, role in zip(palette.color_ramp.elements, ('ink', 'stock')):
            element.color = (*p['printPalette'][role], 1)
        connect(t, textures['artwork'], 'Color', palette, 'Fac')
        connect(t, palette, 'Color', printed, 'Base Color')
    else:
        connect(t, textures['artwork'], 'Color', printed, 'Base Color')
    line = ramp(t, 'Line Mask / Black Ink to White', -200, -250,
                p['lineBlack'], p['lineWhite'], invert=True)
    connect(t, textures['lineart'], 'Color', line, 'Fac')
    gold = node(t, 'ShaderNodeEmission', 'Gold Emission / Tune Color and Strength', 150, -420)
    gold.inputs['Color'].default_value = (*p['color'], 1)
    gold.inputs['Strength'].default_value = p['emission']
    detail = node(t, 'ShaderNodeMixShader', 'Gold Lines Only', 410, -80)
    connect(t, line, 'Color', detail, 0)
    connect(t, printed, 'BSDF', detail, 1)
    connect(t, gold, 0, detail, 2)

    group = bpy.data.node_groups.new('Gold Foil / Reflection Sweep', 'ShaderNodeTree')
    group.interface.new_socket(name='Sweep', in_out='OUTPUT', socket_type='NodeSocketFloat')
    coords = node(group, 'ShaderNodeTexCoord', 'Reflection + Stable UV Grain', -1000, 200)
    mapping = node(group, 'ShaderNodeMapping', 'Sweep Direction / Degrees in Config', -770, 300)
    mapping.inputs['Rotation'].default_value = [math.radians(v) for v in p['mappingRotation']]
    connect(group, coords, 'Reflection', mapping, 'Vector')
    noise = node(group, 'ShaderNodeTexNoise', 'Fine Foil Grain', -770, -140)
    noise.inputs['Scale'].default_value = p['noiseScale']
    noise.inputs['Detail'].default_value = 2
    connect(group, coords, 'UV', noise, 'Vector')
    grain = math_node(group, 'MULTIPLY', 'Grain Amount', -520, -100, p['noiseAmount'])
    connect(group, noise, 'Fac', grain, 0)
    add = math_node(group, 'ADD', 'Mean Mapped Reflection + Grain', -300, 300)
    connect(group, mapping, 'Vector', add, 0)
    connect(group, grain, 0, add, 1)
    phase = math_node(group, 'ADD', 'Sweep Phase', -90, 300, p['phase'])
    connect(group, add, 0, phase, 0)
    repeat = math_node(group, 'MULTIPLY', 'Band Repeat', 110, 300, p['repeat'])
    connect(group, phase, 0, repeat, 0)
    ping = math_node(group, 'PINGPONG', 'Ping-Pong / Triangle Wave', 310, 300, 1)
    connect(group, repeat, 0, ping, 0)
    band = ramp(group, 'Sweep Width', 510, 300, p['sweepBlack'], p['sweepWhite'])
    connect(group, ping, 0, band, 'Fac')
    out = node(group, 'NodeGroupOutput', 'Sweep', 850, 300)
    connect(group, band, 'Color', out, 'Sweep')
    sweep = node(t, 'ShaderNodeGroup', 'Angle Mask / Enter to Tune', 380, 340)
    sweep.node_tree = group
    mix = node(t, 'ShaderNodeMixShader', 'Angle-Selected Gold Detail', 680, 120)
    connect(t, sweep, 'Sweep', mix, 0)
    connect(t, printed, 'BSDF', mix, 1)
    connect(t, detail, 0, mix, 2)
    output = node(t, 'ShaderNodeOutputMaterial', 'Surface', 930, 120)
    connect(t, mix, 0, output, 'Surface')
    return mat


def aim(obj, target=(0, 0, 0)):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def build(project, output, skip_render=False):
    cfg, params, paths, width, samples = configuration(project)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Output must be a new or empty directory; nothing was overwritten')
    images = {}
    for role, path in paths.items():
        im = bpy.data.images.load(str(path), check_existing=False)
        im.colorspace_settings.name = 'Non-Color' if role == 'lineart' or 'printPalette' in params else 'sRGB'
        pixels = array('f', [0]) * len(im.pixels)
        im.pixels.foreach_get(pixels)
        if not pixels or min(pixels[3::4]) < .999:
            raise ValueError(f'{role}: complete opaque artwork is required, not a cutout')
        contrast = max(max(pixels[channel::4]) - min(pixels[channel::4]) for channel in range(3))
        if contrast < .05:
            raise ValueError(f'{role}: image has no usable contrast')
        values = pixels[0::4]
        if role == 'lineart' and (min(values) > params['lineBlack'] or max(values) < .9):
            raise ValueError('lineart: expected black lines and a white background')
        images[role] = im
    if tuple(images['artwork'].size) != tuple(images['lineart'].size):
        raise ValueError('artwork and lineart must have identical canvas dimensions')
    w, h = images['artwork'].size
    if not .3 <= w / h <= 1:
        raise ValueError('Use a portrait card with width/height between 0.3 and 1')
    # This CLI runs in --factory-startup, never against the user's open scene.
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = width
    scene.render.resolution_y = round(width * h / w)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'AgX'
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.025, .03, .04, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .35
    # XY face, +Z normal, front camera +Z. This is independent of holo-card-studio's axes.
    card_w, card_h = 6 * w / h, 6
    mesh = bpy.data.meshes.new('Card Face / Registered UV')
    mesh.from_pydata([(-card_w/2, -3, 0), (card_w/2, -3, 0),
                      (card_w/2, 3, 0), (-card_w/2, 3, 0)], [], [(0, 1, 2, 3)])
    mesh.update()
    uv = mesh.uv_layers.new(name='UVMap')
    for loop, co in zip(uv.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = co
    card = bpy.data.objects.new('Gold Card / Rotate to Inspect', mesh)
    scene.collection.objects.link(card)
    mesh.materials.append(material(images, params))
    edge = bpy.data.materials.new('Gold Edge / Back')
    edge.use_nodes = True
    bsdf = edge.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (.38, .18, .035, 1)
    bsdf.inputs['Metallic'].default_value = 1
    bsdf.inputs['Roughness'].default_value = .3
    mesh.materials.append(edge)
    solid = card.modifiers.new('Thin Card Stock', 'SOLIDIFY')
    solid.thickness, solid.offset = .025, -1
    solid.material_offset = solid.material_offset_rim = 1
    bevel = card.modifiers.new('Soft Physical Edge', 'BEVEL')
    bevel.width, bevel.segments = .008, 3
    scene.render.fps = 24
    scene.frame_end = 72
    for frame, tilt in [(1, 0), (25, -18), (49, 18), (72, 0)]:
        card.rotation_euler = (math.radians(-5), math.radians(tilt), 0)
        card.keyframe_insert('rotation_euler', frame=frame)
    bpy.ops.object.camera_add(location=(0, 0, 13))
    scene.camera = bpy.context.object
    # A flat card under an orthographic camera has one reflection direction everywhere.
    # Perspective is necessary for spatial bands, not just whole-card angle flickering.
    scene.camera.data.type = 'PERSP'
    scene.camera.data.sensor_fit = 'VERTICAL'
    scene.camera.data.lens = 45
    aim(scene.camera)
    for location, power, size in [((-3, 4, 7), 700, 7), ((4, -1, 5), 350, 5)]:
        bpy.ops.object.light_add(type='AREA', location=location)
        light = bpy.context.object
        light.data.energy, light.data.shape, light.data.size = power, 'DISK', size
        aim(light)
    scene.use_nodes = True
    t = scene.node_tree
    t.nodes.clear()
    render = node(t, 'CompositorNodeRLayers', 'Render', 0, 0)
    glow = node(t, 'CompositorNodeGlare', 'Gold Fog Glow', 240, 0)
    glow.glare_type, glow.quality, glow.threshold, glow.size = 'FOG_GLOW', 'HIGH', 1.5, 7
    final = node(t, 'CompositorNodeComposite', 'Final', 480, 0)
    connect(t, render, 'Image', glow, 'Image')
    connect(t, glow, 'Image', final, 'Image')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'renders').mkdir(exist_ok=True)
    for role, im in images.items():
        im.pack()
        im.filepath = f'//assets/{role}.png'
    scene['Title'] = str(cfg.get('title', 'Gold Foil Card'))
    scene['Method'] = 'BV1K1doB5Eq3: reflection + grain + ping-pong sweep + line emission; independent tunable reconstruction'
    scene['Parameters'] = json.dumps(params, ensure_ascii=False)
    scene.frame_set(1)
    bpy.ops.object.select_all(action='DESELECT')
    card.select_set(True)
    bpy.context.view_layer.objects.active = card
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
    scene.render.filepath = str(output / 'renders' / 'front.png')
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'gold-card.blend'))
    for name, frame in ([] if skip_render else [('front', 1), ('left', 25), ('right', 49)]):
        scene.frame_set(frame)
        scene.render.filepath = str(output / 'renders' / f'{name}.png')
        bpy.ops.render.render(write_still=True)
    report = {'status': 'built-not-rendered' if skip_render else 'rendered-needs-visual-review',
              'blender': bpy.app.version_string, 'title': scene['Title'], 'gold': params,
              'source': 'https://www.bilibili.com/video/BV1K1doB5Eq3/',
              'canvas': [w, h], 'packedImages': 2,
              'render': {'width': width, 'samples': samples}}
    (output / 'build-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Built:', output / 'gold-card.blend')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--skip-render', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    build(Path(args.project).resolve(), Path(args.output).resolve(), args.skip_render)
