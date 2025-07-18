import contextlib
import hashlib
import pathlib
import sys
from dataclasses import dataclass, field, fields
from typing import Any, Dict, Generator, Hashable, Optional, Set, Tuple

from typing_extensions import Protocol


class Hasher(Protocol):
    def __call__(self, obj: bytes) -> int:
        pass


class HasherFromHashlibHasher(Hasher):
    def __init__(self, hashlib_hasher: Any, hash_length_bits: int) -> None:
        self.hashlib_hasher = hashlib_hasher
        self.hash_length_bits = hash_length_bits
        if not hash_length_bits % 8 == 0:
            raise RuntimeError("Must hash an even number of bytes")

    def __call__(self, obj: bytes) -> int:
        hashlib_hasher_instance = self.hashlib_hasher(
            digest_size=self.hash_length_bits // 8
        )
        hashlib_hasher_instance.update(obj)
        return int.from_bytes(hashlib_hasher_instance.digest(), "big")


@dataclass
class Config:
    def __setattr__(self, attr: str, val: Any) -> None:
        if attr in {field.name for field in fields(self.__class__)}:
            object.__setattr__(self, attr, val)
        else:
            raise AttributeError(f"{attr} does not exist on {self.__class__.__name__}")

    recursion_limit: Optional[int] = 50

    ignore_module_attrs: Set[str] = field(
        default_factory=lambda: {
            "__builtins__",
            "__cached__",
            "__doc__",
            "__file__",
            "__loader__",
            "__spec__",
        }
    )

    # Put ``(module, global_name)`` of which never change or whose changes do
    # not affect the result computation here (e.g. global caches). This will not
    # attempt to freeze their state.
    ignore_globals: Set[Tuple[str, str]] = field(
        default_factory=lambda: {
            # tempdir caches the name of the temporary directory on this platorm.
            ("tempfile", "tempdir"),
            # thread status variables don't directly affect computation.
            ("threading", "_active"),
            ("threading", "_limbo"),
            ("re", "_cache"),
            ("charmonium.freeze.lib", "global_config"),
            ("sys", "modules"),
            ("sys", "path"),
            ("linecache", "cache"),
            ("inspect", "_filesbymodname"),
            ("inspect", "modulesbyfile"),
            ("sre_compile", "compile"),
            ("os", "environ"),
        }
    )

    # Use the version instead of attributes (slow), when module's version
    # metadata is available.
    use_version: bool = True

    # If use_version is True, these are the exceptions.
    #
    # This would be useful if you have a versioned, but in-development modoule,
    # whose version does not completely specify the contents. Put that module's
    # name here to guarantee soundness.
    use_version_exceptions: Set[str] = field(default_factory=set)

    # Put ``(function.__module__, function.__name__, nonlocal_name)`` of
    # nonlocal variables which never change or whose changes do not affect the
    # result computation here, (e.g. caches). This will not attempt to freeze
    # their state. Note that the module and name may be different than the
    # identifier you use to import the function. Use ``function.__module__`` and
    # ``function.__name__`` to be sure.
    ignore_nonlocals: Set[Tuple[str, str]] = field(
        default_factory=lambda: {
            # Special case for functools.single_dispatch: We need to ignore the
            # following non-locals, as their mutation do not affect the actual
            # computation.
            ("functools", "cache_token"),
            ("functools", "dispatch_cache"),
        }
    )

    # Put paths to source code that whose source code never changes or those
    # changes do not affect the result computation. I will still recurse into
    # the closure of these functions, just not its source code though.
    ignore_files: Set[pathlib.Path] = field(default_factory=set)

    # These modules are versioned by the Python version
    stdlib_modules: Set[str] = field(
        default_factory=lambda: {*sys.stdlib_module_names, *sys.builtin_module_names},
    )

    assume_purity: bool = True

    @property
    def assume_impurity(self) -> bool:
        return not self.assume_purity

    override_impure_modules: Set[str] = field(
        default_factory=lambda: {
            "random",
        },
    )

    override_pure_modules: Set[str] = field(
        default_factory=lambda: {
            "re",
            "urllib.parse",
            "charmonium.freeze",
        },
    )

    # Whether to assume that all code is constant
    ignore_all_code: bool = False

    # Put ``(object.__module__, object.__class__.__name__, attribute)`` of
    # object attributes which never change or whose changes do not affect the
    # result computation here (e.g. cached attributes). This will not attempt to
    # freeze their state. Note that the module may be different than the name
    # you import it as. Use ``object.__module__`` to be sure.
    ignore_attributes: Set[Tuple[str, str, str]] = field(
        default_factory=lambda: {
            ("pandas.core.internals.blocks", "Block", "_cache"),
            ("tqdm.std", "tqdm", "fp"),
            ("tqdm.std", "tqdm", "sp"),
            ("tqdm.std", "tqdm", "pos"),
            ("tqdm.std", "tqdm", "last_print_t"),
            ("tqdm.std", "tqdm", "start_t"),
        }
    )

    # Put ``(object.__module__, object.__class__.__name__)`` of objects which do
    # not affect the result computation here (e.g. caches, locks, and
    # threads). Use ``object.__module__`` and ``object.__class__.__name__`` to
    # be sure.
    ignore_objects_by_class: Set[Tuple[str, str]] = field(
        default_factory=lambda: {
            ("builtins", "_abc_data"),
            ("_abc", "_abc_data"),
            ("_thread", "RLock"),
            ("_thread", "LockType"),
            ("_thread", "lock"),
            ("_thread", "_local"),
            ("threading", "local"),
            ("multiprocessing.synchronize", "Lock"),
            ("multiprocessing.synchronize", "RLock"),
            ("builtins", "weakref"),
            ("builtins", "PyCapsule"),
            ("weakref", "WeakKeyDictionary"),
            ("weakref", "WeakValueDictionary"),
            ("weakref", "WeakSet"),
            ("weakref", "KeyedRef"),
            ("weakref", "WeakMethod"),
            ("weakref", "ReferenceType"),
            ("weakref", "ProxyType"),
            ("weakref", "CallableProxyType"),
            ("_weakrefset", "WeakSet"),
            ("threading", "Thread"),
            ("threading", "Event"),
            ("threading", "_DummyThread"),
            ("threading", "Condition"),
            ("typing", "Generic"),
            ("re", "RegexFlag"),
            # see https://github.com/python/cpython/issues/92049
            ("sre_constants", "_NamedIntConstant"),
            # TODO: [research] Remove these when we have caching
            # They are purely performance (not correctness)
            ("pandas.core.dtypes.base", "Registry"),
        }
    )

    # Put ``id(object)`` of objects which do not affect the result computation
    # here, especially those which mutate or are not picklable. Prefer to use
    # ``config.ignore_objects_by_class`` if applicable.
    ignore_objects_by_id: Set[int] = field(default_factory=set)

    # Whether to ignore all classes
    ignore_all_classes: bool = False

    # Put ``(class.__module__, class.__name__)`` of classes whose source code
    # and class attributes never change or those changes do not affect the
    # result computation.
    ignore_classes: Set[Tuple[str, Optional[str]]] = field(
        default_factory=lambda: {
            # TODO: [research] See if we can reduce these
            ("tqdm.std", "tqdm"),
            ("re", "RegexFlag"),
            ("re", "Pattern"),
            ("pathlib", None),
            ("builtins", None),
            ("ABC", None),
            ("ABCMeta", None),
            ("_operator", None),
            ("numpy", "ndarray"),
            ("pandas.core.frame", "DataFrame"),
            ("pandas.core.series", "Series"),
            ("pandas.core.indexes.base", "Index"),
            ("matplotlib.figure", "Figure"),
            ("typing", "Generic"),
        }
    )

    ignore_dict_order: bool = False

    log_width: int = 250

    memo: Dict[int, Hashable] = field(default_factory=dict)

    special_class_attributes: Set[str] = field(
        default_factory=lambda: {
            "__orig_bases__",
            "__dict__",
            "__weakref__",
            "__doc__",
            "__parameters__",
            "__slots__",
            "__slotnames__",
            "__mro_entries__",
            "__annotations__",
            "__hash__",
            # Some scripts are designed to be either executed or imported.
            # In that case, the __module__ can be either __main__ or a qualified module name.
            # As such, I exclude the name of the module containing the class.
            "__module__",
        }
    )

    hasher: Hasher = HasherFromHashlibHasher(hashlib.blake2s, 64)
    use_hash: bool = True
    hash_length: int = 64


global_config = Config()


@contextlib.contextmanager
def global_config_ctx(**kwargs: Any) -> Generator[None, None, None]:
    global global_config
    old_global_config = global_config
    global_config = Config(**kwargs)
    try:
        yield
    finally:
        global_config = old_global_config
