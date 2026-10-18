"""Execute the unchanged scalar source equations without decorating them.

Only decorator/import nodes are removed. All function bodies remain identical
and refer to the other original scalar functions, never to the native backend.
The transformed module is isolated; production Numba dispatchers are untouched.
"""
import ast
from functools import lru_cache
from pathlib import Path
from types import ModuleType
import sys
import importlib
import importlib.util
import os


@lru_cache(maxsize=3)
def scalar_module(name):
    if name not in ('discrete_operator', 'cspace', 'joint_transition'):
        raise ValueError('unknown scalar source module')
    compiled='nohit.engine._scalar_'+name
    if os.environ.get('NOHIT_SCALAR_PYTHON')!='1' and importlib.util.find_spec(compiled) is not None:
        return importlib.import_module(compiled)
    path = Path(__file__).with_name(name + '.py')
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    tree.body = [node for node in tree.body
                 if not (isinstance(node, ast.ImportFrom) and node.module == 'numba')]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.decorator_list = [decorator for decorator in node.decorator_list
                                   if not (isinstance(decorator, ast.Call)
                                           and isinstance(decorator.func, ast.Name)
                                           and decorator.func.id == 'njit')]
    if name == 'joint_transition':
        tree.body = [node for node in tree.body if not (isinstance(node, ast.ImportFrom)
            and node.module in ('discrete_operator', 'cspace'))]
    module = ModuleType('nohit.engine._scalar_' + name)
    module.__file__ = str(path)
    module.__package__ = 'nohit.engine'
    sys.modules[module.__name__] = module
    if name == 'joint_transition':
        module.__dict__.update(step_mask_into=scalar_module('discrete_operator').step_mask_into,
            sample_position=scalar_module('discrete_operator').sample_position,
            collision_query=scalar_module('cspace').collision_query)
    exec(compile(tree, str(path), 'exec'), module.__dict__)
    return module
