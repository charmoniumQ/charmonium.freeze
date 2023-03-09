from __future__ import annotations

import types
from pathlib import Path
from typing import Any, Dict, Hashable, Optional, Tuple

from . import util
from .config import Config
from .lib import freeze_attrs, freeze_dispatch, freeze_sequence, logger


@freeze_dispatch.register
def _(
    obj: types.FunctionType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    type_pair = (obj.__module__, obj.__name__)
    if type_pair in config.ignore_functions:
        logger.debug("%s ignoring %s", " " * depth, type_pair)
        return freeze_sequence(type_pair, True, True, config, tabu, depth)
    closure = util.get_closure_attrs(obj)
    attrs: Dict[str, Any] = {}
    attrs["code"] = obj.__code__
    myglobals = {
        ".".join((var_name, *attr_path)): val
        for var_name, attr_path, _, val in closure.myglobals
        if (obj.__module__, var_name) not in config.ignore_globals
        and (not attr_path or (var_name, attr_path[0]) not in config.ignore_globals)
    }
    if myglobals:
        attrs["globals"] = myglobals
    nonlocals = {
        ".".join((var_name, *attr_path)): val
        for var_name, attr_path, _, val in closure.nonlocals
        if (
            (obj.__module__, var_name) not in config.ignore_nonlocals
            and (
                not attr_path
                or (obj.__module__, attr_path[0]) not in config.ignore_nonlocals
            )
        )
    }
    if nonlocals:
        attrs["nonlocals"] = nonlocals
    return freeze_attrs(attrs, True, False, config, tabu, depth)


@freeze_dispatch.register
def _(
    obj: types.CodeType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_code(obj, config, tabu, depth, index)


def freeze_code(
    obj: types.CodeType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    _index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    source_loc = Path(obj.co_filename)
    if config.ignore_all_code or any(
        util.is_relative_to(source_loc, constant_file)
        for constant_file in config.ignore_files
    ):
        if config.use_hash:
            return config.hasher(obj.co_name.encode()), True, None
        else:
            return obj.co_name, True, None
    return freeze_sequence(
        (obj.co_name, *obj.co_consts, obj.co_code), True, True, config, tabu, depth
    )


@freeze_dispatch.register
def _(
    obj: types.FrameType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_frame(obj, config, tabu, depth, index)


def freeze_frame(
    obj: types.FrameType,
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_sequence(
        (obj.f_code, obj.f_locals, obj.f_lasti),
        is_immutable=True,
        order_matters=True,
        config=config,
        tabu=tabu,
        depth=depth,
    )
    # return freeze_sequence(
    #     (obj.f_code, obj.f_locals, obj.f_lasti),
    #     is_immutable=True,
    #     order_matters=True,
    #     config=config,
    #     tabu=tabu,
    #     depth=depth,
    # )


@freeze_dispatch.register
def _(
    obj: types.BuiltinFunctionType,
    config: Config,
    _tabu: Dict[int, Tuple[int, int]],
    _depth: int,
    _index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    if config.use_hash:
        return config.hasher(obj.__name__.encode()), True, None
    return obj.__name__, True, None


@freeze_dispatch.register(types.GeneratorType)
def _(
    obj: types.GeneratorType[Any, Any, Any],
    config: Config,
    tabu: Dict[int, Tuple[int, int]],
    depth: int,
    index: int,
) -> Tuple[Hashable, bool, Optional[int]]:
    return freeze_frame(obj.gi_frame, config, tabu, depth, 0)
