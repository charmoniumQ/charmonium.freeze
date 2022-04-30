import types
from pathlib import Path
import sys
from typing import Any, Hashable

from .lib import _freeze, config, freeze_dispatch, immutable_if_children_are, logger
from .util import Ref
from . import util


@freeze_dispatch.register(type)
def _(
    obj: type[Any], tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    assert obj == obj.__mro__[0]
    type_pair = (obj.__module__, obj.__name__)
    if (
        (type_pair[0], None) in config.ignore_classes
        or type_pair in config.ignore_classes
        or obj is object
        # or (config.ignore_extensions and (
        #     not getattr(obj, "__module__", None)
        #     or (obj.__module__ != "__main__" and not getattr(sys.modules.get(object.__module__), "__file__", None))
        # ))
    ):
        logger.debug("%s ignoring %s", " " * depth, type_pair)
        return type_pair, True
    is_immutable = Ref(True)
    ret = (
        b"class",
        ("__name__", obj.__name__),
        *(
            (
                # TODO: don't freeze var
                _freeze(var, tabu, depth, index)[0],
                immutable_if_children_are(_freeze(val, tabu, depth, index), is_immutable),
            )
            for index, (var, val) in enumerate(sorted(obj.__dict__.items()))
            if var not in special_class_attributes
            and (obj.__module__, obj.__name__, var) not in config.ignore_attributes
        )
    )
    superclass: tuple[Hashable, ...]
    if len(obj.__mro__) > 1:
        superclass = (
            immutable_if_children_are(
                _freeze(obj.__mro__[1], tabu, depth, index), is_immutable
            ),
        )
    else:
        superclass = ()
    return (ret, *superclass), is_immutable()


# TODO: Put this in config
# Also note that the presence of these attributes implies a class is not immutable
special_class_attributes = {
    "__orig_bases__",
    "__dict__",
    "__weakref__",
    "__doc__",
    "__parameters__",
    "__slots__",
    "__slotnames__",
    "__mro_entries__",
    # Some scripts are designed to be either executed or imported.
    # In that case, the __module__ can be either __main__ or a qualified module name.
    # As such, I exclude the name of the module containing the class.
    "__module__",
}


@freeze_dispatch.register
def _(
    obj: types.FunctionType, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    type_pair = (obj.__module__, obj.__name__)
    if type_pair in config.ignore_functions:
        logger.debug("%s ignoring %s", " " * depth, type_pair)
        return type_pair, True
    closure = util.get_closure_attrs(obj)
    is_immutable = Ref(True)
    nonlocals = [
        (
            # TODO: var is already a string
            _freeze(".".join((var, *attr_path)), tabu, depth, index)[0],
            immutable_if_children_are(_freeze(val, tabu, depth, index), is_immutable),
        )
        for var, attr_path, _, val in sorted(closure.nonlocals)
        if (obj.__module__, obj.__name__, var) not in config.ignore_nonlocals
    ]
    myglobals = [
        (
            # TODO: var is already a string
            ".".join((var, *attr_path)),
            _freeze(".".join((var, *attr_path)), tabu, depth, index)[0],
            immutable_if_children_are(_freeze(val, tabu, depth, index), is_immutable),
        )
        for var, attr_path, _, val in sorted(closure.myglobals)
        if (obj.__module__, var) not in config.ignore_globals
    ]
    return (
        b"function",
        _freeze(obj.__code__, tabu, depth, index)[0],
        tuple(nonlocals),
        tuple(myglobals),
    ), is_immutable()


@freeze_dispatch.register
def _(
    obj: types.CodeType, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    source_loc = Path(obj.co_filename)
    if any(
        util.is_relative_to(source_loc, constant_file)
        for constant_file in config.assume_constant_files
    ):
        return (
            b"code",
            obj.co_name,
        ), True
    else:
        is_immutable = Ref(True)
        constants = tuple(
            immutable_if_children_are(_freeze(const, tabu, depth, index), is_immutable)
            for index, const in enumerate(obj.co_consts)
        )
        return (
            "code",
            obj.co_name,
            obj.co_code,
            constants,
        ), is_immutable()


@freeze_dispatch.register
def _(
    obj: types.FrameType, tabu: dict[int, tuple[int, int]], depth: int, index: int
) -> tuple[Hashable, bool]:
    code = _freeze(obj.f_code, tabu, depth, index)[0]
    is_immutable = Ref(True)
    all_vars = tuple(
        (var, immutable_if_children_are(_freeze(val, tabu, depth, index), is_immutable))
        for var, val in sorted(obj.f_locals.items())
    )
    return (code, *all_vars, obj.f_lasti), is_immutable()
