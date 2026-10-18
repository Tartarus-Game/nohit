"""Compile source-derived scalar numeric bodies; never cache worlds or routes.

Run once after installing requirements-accelerated.txt. Re-run after changing
an engine source. --remove restores the ordinary interpreter immediately.
"""
import argparse
import ast
import hashlib
import importlib.machinery
import json
import os
import platform
from pathlib import Path
import shutil
import sys
import sysconfig

ROOT=Path(__file__).resolve().parents[1]
ENGINE=ROOT/'nohit/engine'
MODULES=()
LEGACY_VM=('compact_wave','resumable_wave','native_dynamic','source_verification')
SCALARS={'discrete_operator':'discrete_operator','cspace':'cspace','entities':'compact_wave',
    'reference_numeric':'reference_numeric'}


def entity_source(path):
    tree=ast.parse(path.read_text())
    if path.stem=='compact_wave':
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ROOT' for t in node.targets):
                node.value=ast.parse("Path(__import__('nohit').__file__).resolve().parents[1]",mode='eval').body
        fields={'x','y','end_x','end_y','end_ang','angle','timer','blast_time',
            'leave_speed','beam_timer','base_size','opacity','scale_y','scale_x'}
        class FloatFields(ast.NodeTransformer):
            def visit_Attribute(self,node):
                self.generic_visit(node)
                if isinstance(node.ctx,ast.Load) and isinstance(node.value,ast.Name) and node.value.id=='self' and node.attr in fields:
                    return ast.Call(ast.Attribute(ast.Name('cython',ast.Load()),'cast',ast.Load()),
                        [ast.Attribute(ast.Name('cython',ast.Load()),'double',ast.Load()),node],[])
                return node
            def visit_AugAssign(self,node):
                if isinstance(node.target,ast.Attribute) and isinstance(node.target.value,ast.Name) and node.target.value.id=='self' and node.target.attr in fields:
                    old=ast.Attribute(node.target.value,node.target.attr,ast.Load())
                    return ast.Assign([node.target],ast.BinOp(self.visit(old),node.op,self.visit(node.value)))
                return self.generic_visit(node)
        def typed(node,names):
            node.decorator_list+=ast.parse('@cython.locals('+','.join(n+'=cython.double' for n in names.split())+')\ndef f():pass').body[0].decorator_list
        for node in tree.body:
            if isinstance(node,ast.FunctionDef) and node.name=='_blaster_fire_bbox':
                typed(node,'x y ux uy scale_x scale_y width height offset cx cy rx ry')
            if isinstance(node,ast.ClassDef) and node.name=='_ActiveGasterBlaster':
                for method in node.body:
                    if isinstance(method,ast.FunctionDef) and method.name in ('step','polygon'):
                        typed(method,'dt v target a ux uy left top right bottom normalized_opacity compared_opacity' if method.name=='step' else 'a ux uy ax ay hw')
                        method.body=[FloatFields().visit(part) for part in method.body]
    tree.body=[node for node in tree.body if isinstance(node,(ast.ClassDef,ast.FunctionDef))
        and node.name in ('_ActiveGasterBlaster','_blaster_fire_bbox')]
    tree.body[:0]=ast.parse('import math\nimport cython\nfrom .native_numbers import native_int\n').body
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)+'\n'


def scalar_source(path):
    tree=ast.parse(path.read_text())
    tree.body=[node for node in tree.body if not (isinstance(node,ast.ImportFrom) and node.module=='numba')]
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            node.decorator_list=[d for d in node.decorator_list if not
                (isinstance(d,ast.Call) and isinstance(d.func,ast.Name) and d.func.id=='njit')]
    floating={
        'direction_xy':'direction angle',
        'overlaps':'x y l t r b',
        'heart_solid':'x y dy direction ox oy l t r b qx qy active platform_dy',
        'clamp_to_arena':'x y',
        'movement_phase':'x y dx dy slammed direction slam_damage dt damage mx my start candidate',
        'step_mask_into':'x y dx dy slammed damage mode direction max_fall slam_damage dt gx gy slam_speed speed down_speed gravity',
        'advance_bones':'dt x y direction',
        'bone_geometry':'x y left top right bottom',
        'quad_intersects_box':'x y rx ry left right top bottom ax ay lo hi dot mid radius',
        '_rect_hit':'x y radius',
    }
    integers={'heart_solid':'j','clamp_to_arena':'j','movement_phase':'count i',
        'step_mask_into':'mask previous ux up jumpkey','quad_intersects_box':'j k m _index',
        'advance_bones':'read write column count','bone_geometry':'read count nw nb'}
    boolean={'heart_solid':'old','step_mask_into':'captured_slam'}
    class PolyAccess(ast.NodeTransformer):
        def visit_Subscript(self,node):
            self.generic_visit(node)
            if isinstance(node.value,ast.Name) and node.value.id=='poly':node.value.id='p'
            return node
    class RectAccess(ast.NodeTransformer):
        def visit_Subscript(self,node):
            self.generic_visit(node)
            if isinstance(node.value,ast.Name) and node.value.id=='box':
                return ast.Call(ast.Attribute(ast.Name('cython',ast.Load()),'cast',ast.Load()),
                    [ast.Attribute(ast.Name('cython',ast.Load()),'double',ast.Load()),node],[])
            return node
    for node in tree.body:
        if not isinstance(node,ast.FunctionDef) or node.name not in floating:continue
        declarations=[]
        for names,kind in ((floating[node.name],'double'),(integers.get(node.name,''),'int'),(boolean.get(node.name,''),'bint')):
            declarations.extend(name+'=cython.'+kind for name in names.split())
        if node.name in ('advance_bones','bone_geometry'):
            declarations.append('rows=cython.double[:,:]')
        if node.name=='bone_geometry':
            declarations += ['white=cython.double[:,:]','blue=cython.double[:,:]','bounds=cython.double[:]']
        decorators=ast.parse('@cython.ccall\n@cython.locals('+','.join(declarations)+')\ndef f():pass').body[0].decorator_list
        node.decorator_list=decorators+node.decorator_list
        if node.name in ('overlaps','heart_solid','quad_intersects_box','_rect_hit'):
            node.decorator_list.append(ast.parse('@cython.returns(cython.bint)\ndef f():pass').body[0].decorator_list[0])
        if node.name=='quad_intersects_box':
            first=next(i for i,statement in enumerate(node.body) if isinstance(statement,ast.If))
            after=[PolyAccess().visit(statement) for statement in node.body[first+1:]]
            copy=ast.parse('p=cython.declare(cython.double[8])\nfor _index in range(8):p[_index]=poly[_index]').body
            node.body=node.body[:first+1]+copy+after
        if node.name=='_rect_hit':node.body=[RectAccess().visit(statement) for statement in node.body]
    tree.body.insert(1,ast.Import([ast.alias('cython')]))
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remove',action='store_true')
    parser.add_argument('--jobs',type=int,default=4)
    parser.add_argument('--native',action='store_true',help='Install the C++ code image for compiler-free cold starts')
    args=parser.parse_args()
    names=MODULES+tuple('_scalar_'+name for name in SCALARS)
    suffix=sysconfig.get_config_var('EXT_SUFFIX')
    for name in LEGACY_VM:(ENGINE/(name+suffix)).unlink(missing_ok=True)
    if args.remove:
        for name in names:(ENGINE/(name+suffix)).unlink(missing_ok=True)
        for extension in ('.so','.dylib','.dll'):(ENGINE/('_native_frontier'+extension)).unlink(missing_ok=True)
        (ENGINE/'native-build.json').unlink(missing_ok=True)
        return
    from Cython.Build import cythonize
    from Cython import __version__ as cython_version
    from setuptools import Extension,setup
    if os.name != 'nt':
        os.environ.setdefault('CC',shutil.which('gcc') or shutil.which('clang') or 'cc')
    sources={name:hashlib.sha256((ENGINE/(name+'.py')).read_bytes()).hexdigest() for name in set(SCALARS.values())}
    options=dict(cython=cython_version,python=sys.version,platform=sysconfig.get_platform(),compiler=os.environ.get('CC','msvc'),
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        sources=sources,directives=dict(language_level=3,annotation_typing=False,binding=True),
        flags=['/O2','/fp:strict'] if os.name=='nt' else ['-O2','-g0','-ffp-contract=off','-fno-fast-math'])
    identity=hashlib.sha256(json.dumps(options,sort_keys=True).encode()).hexdigest()
    cache=ROOT/'build/accelerated'/identity
    generated=cache/'generated';generated.mkdir(parents=True,exist_ok=True)
    previous_path=ROOT/'build/accelerated/manifest.json'
    previous=json.loads(previous_path.read_text()) if previous_path.exists() else {}
    compatible=all(previous.get(key)==options[key] for key in ('cython','python','platform','compiler','directives','flags','generator_sha256'))
    if compatible:
        for name in names:
            source=SCALARS[name.removeprefix('_scalar_')]
            old=ENGINE/(name+suffix);target=cache/'lib/nohit/engine'/(name+suffix)
            if (not target.exists() and old.exists() and previous.get('sources',{}).get(source)==sources[source]
                    and hashlib.sha256(old.read_bytes()).hexdigest()==previous.get('binaries',{}).get(name)):
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,target)
    extensions=[]
    for name,source in SCALARS.items():
        target=generated/('_scalar_'+name+'.py')
        target.write_text((entity_source if name=='entities' else scalar_source)(ENGINE/(source+'.py')))
        if not (cache/'lib/nohit/engine'/('_scalar_'+name+suffix)).exists():
            extensions.append(Extension('nohit.engine._scalar_'+name,[str(target)],extra_compile_args=options['flags']))
    if not all((cache/'lib/nohit/engine'/(name+suffix)).exists() for name in names):
        extensions=cythonize(extensions,compiler_directives=options['directives'],
            build_dir=str(generated/'cython'),quiet=True)
        setup(name='nohit-local-accelerators',ext_modules=extensions,
            script_args=['build_ext','--build-lib',str(cache/'lib'),'--build-temp',str(cache/'temp'),'-j',str(args.jobs)])
    binaries={}
    for name in names:
        built=cache/'lib/nohit/engine'/(name+suffix);installed=ENGINE/(name+suffix)
        installed.unlink(missing_ok=True)
        try:installed.symlink_to(built)
        except OSError:shutil.copy2(built,installed)
        binaries[name]=hashlib.sha256(built.read_bytes()).hexdigest()
    for name in LEGACY_VM:(ENGINE/(name+suffix)).unlink(missing_ok=True)
    (ROOT/'build/accelerated/manifest.json').write_text(json.dumps(dict(options,identity=identity,binaries=binaries),indent=2)+'\n')
    if args.native:
        from nohit.engine.native_backend import load_backend
        library,native=load_backend();source=Path(library._name)
        destination=ENGINE/('_native_frontier'+source.suffix)
        if source.resolve()!=destination.resolve():shutil.copy2(source,destination)
        native=dict(native,binary_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
            system=platform.system(),machine=platform.machine())
        (ENGINE/'native-build.json').write_text(json.dumps(native,indent=2)+'\n')
    print(json.dumps(dict(identity=identity,modules=list(binaries))))


if __name__=='__main__':main()
