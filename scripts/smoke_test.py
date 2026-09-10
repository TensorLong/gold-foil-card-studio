"""One offline end-to-end check. Outer Python needs Pillow; Blender needs no addon."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def inside(project):
    import bpy
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_card import build, configuration

    output = project / 'output'
    build(project, output)
    try:
        build(project, output)
        raise AssertionError('Existing output was accepted')
    except ValueError as error:
        assert 'nothing was overwritten' in str(error)
    config_path = project / 'card-config.json'
    original = config_path.read_text()
    for change in [{'assets': {'artwork': '../escape.png'}},
                   {'gold': {'repeat': float('nan')}},
                   {'printPalette': {'ink': [0, 0, float('nan')], 'stock': [1, 1, 1]}},
                   {'gold': {'sweepBlack': .9, 'sweepWhite': .1}}]:
        config_path.write_text(json.dumps(change))
        try:
            configuration(project)
            raise AssertionError('Invalid input was accepted')
        except ValueError:
            pass
    config_path.write_text(original)

    # Reopen the saved artifact, proving checks concern the delivered scene.
    bpy.ops.wm.open_mainfile(filepath=str(output / 'gold-card.blend'))
    assert sum(bool(im.packed_file) for im in bpy.data.images) == 2
    scene = bpy.context.scene
    assert scene.camera.data.type == 'PERSP', 'Perspective is required for spatial reflection bands'
    mat = bpy.data.materials['Gold Foil Card / Printed Art + Gold Lines']
    t = mat.node_tree
    palette = t.nodes['Full Gold / Registered Master Palette']
    assert tuple(palette.color_ramp.elements[1].color)[:3] == (.75, .5, .25)
    assert palette.outputs['Color'].is_linked
    group = bpy.data.node_groups['Gold Foil / Reflection Sweep']
    assert any(link.from_socket.name == 'Reflection' for link in group.links)
    assert group.nodes['Ping-Pong / Triangle Wave'].operation == 'PINGPONG'
    assert group.nodes['Band Repeat'].operation == 'MULTIPLY'
    assert bpy.data.images.get('lineart.png').colorspace_settings.name == 'Non-Color'
    scene.frame_set(1)
    final_mix = t.nodes['Angle-Selected Gold Detail']
    sweep_link = final_mix.inputs[0].links[0]
    source = sweep_link.from_socket
    t.links.remove(sweep_link)
    final_mix.inputs[0].default_value = 0
    scene.render.filepath = str(output / 'renders' / 'no-gold.png')
    bpy.ops.render.render(write_still=True)
    t.links.new(source, final_mix.inputs[0])

    line_ramp = t.nodes['Line Mask / Black Ink to White'].color_ramp
    for element in line_ramp.elements:
        element.color = (0, 0, 0, 1)
    # Use a deterministic black print branch, isolating masking from Cycles BSDF noise.
    printed = t.nodes['Printed Artwork']
    print_targets = [link.to_socket for link in t.links if link.from_node == printed]
    black = t.nodes.new('ShaderNodeEmission')
    black.inputs['Color'].default_value = (0, 0, 0, 1)
    for socket in print_targets:
        t.links.new(black.outputs[0], socket)
    scene.use_nodes = False
    scene.render.dither_intensity = 0
    scene.render.filepath = str(output / 'renders' / 'no-lines.png')
    bpy.ops.render.render(write_still=True)
    # Show only the angle mask at three rotations; center samples stay on the face.
    emission = t.nodes.new('ShaderNodeEmission')
    t.links.new(source, emission.inputs['Color'])
    emission.inputs['Strength'].default_value = 1
    t.links.new(emission.outputs[0], t.nodes['Surface'].inputs['Surface'])
    for frame, name in [(1, 'front'), (25, 'left'), (49, 'right')]:
        scene.frame_set(frame)
        scene.render.filepath = str(output / 'renders' / f'sweep-{name}.png')
        bpy.ops.render.render(write_still=True)
    # Diagnostics are deliberately not saved back into the editable .blend.


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--blender', required=True)
    args = p.parse_args()
    from PIL import Image, ImageDraw, ImageChops, ImageStat
    project = Path(tempfile.mkdtemp(prefix='gold-foil-check-'))
    assets = project / 'assets'
    assets.mkdir()
    size = (256, 384)
    art = Image.new('RGB', size, '#e7ddc4')
    lines = Image.new('RGB', size, 'white')
    a, l = ImageDraw.Draw(art), ImageDraw.Draw(lines)
    for painter, ink in [(a, '#384747'), (l, 'black')]:
        painter.rounded_rectangle((12, 12, 244, 372), radius=15, outline=ink, width=2)
        painter.ellipse((41, 98, 215, 272), outline=ink, width=3)
        painter.ellipse((72, 129, 184, 241), outline=ink, width=2)
        painter.polygon([(128, 107), (143, 169), (205, 185), (143, 201),
                         (128, 263), (113, 201), (51, 185), (113, 169)], outline=ink, width=2)
        painter.text((91, 44), 'GOLD / 01', fill=ink)
        painter.text((82, 320), 'MATERIAL TEST', fill=ink)
    art.save(assets / 'artwork.png')
    lines.save(assets / 'lineart.png')
    (project / 'card-config.json').write_text(json.dumps({
        'title': 'Original geometric material test - not a finished user card',
        'printPalette': {'ink': [.125, .0625, 0], 'stock': [.75, .5, .25]},
        'render': {'width': 192, 'samples': 8}}))
    command = [args.blender, '--background', '--factory-startup', '--python-exit-code', '1',
               '--python', str(Path(__file__).resolve()), '--', '--inside', str(project)]
    print('Test output:', project, flush=True)
    with (project / 'blender.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Blender failed ({result.returncode}); inspect {project / "blender.log"}')
    renders = project / 'output' / 'renders'
    front = Image.open(renders / 'front.png').convert('RGB')
    baseline = Image.open(renders / 'no-gold.png').convert('RGB')
    effect = sum(ImageStat.Stat(ImageChops.difference(front, baseline)).mean) / 3
    assert effect > .5, f'Gold on/off produced no visible effect: {effect}'
    no_lines = Image.open(renders / 'no-lines.png').convert('RGB')
    center = no_lines.crop((no_lines.width//4, no_lines.height//4,
                            no_lines.width*3//4, no_lines.height*3//4))
    leakage = max(ImageStat.Stat(center).mean)
    assert leakage == 0, f'Gold escaped the zero-line mask: {leakage}'
    means = []
    for name in ('front', 'left', 'right'):
        im = Image.open(renders / f'sweep-{name}.png').convert('L')
        cx, cy = im.width // 2, im.height // 2
        means.append(ImageStat.Stat(im.crop((cx-12, cy-12, cx+12, cy+12))).mean[0])
    assert max(means) - min(means) > 15, f'Angle mask did not move: {means}'
    sheet = Image.new('RGB', (front.width * 3, front.height), '#101010')
    for index, name in enumerate(('left', 'front', 'right')):
        sheet.paste(Image.open(renders / f'{name}.png').convert('RGB'), (front.width * index, 0))
    sheet.save(project / 'contact-sheet.png')
    report = {'status': 'PASS', 'goldOnOffMeanDifference': effect, 'lineMaskLeakage': leakage,
              'sweepCenterMeansFrontLeftRight': means, 'output': str(project),
              'checks': ['packed-scene reopen', 'node topology', 'data color space',
                         'overwrite refusal', 'path escape refusal', 'finite/range checks',
                         'three-angle renders', 'same-angle gold on/off', 'zero-line mask', 'angle-mask renders']}
    (project / 'smoke-result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    if '--inside' in sys.argv:
        inside(Path(sys.argv[sys.argv.index('--inside') + 1]).resolve())
    else:
        main()
