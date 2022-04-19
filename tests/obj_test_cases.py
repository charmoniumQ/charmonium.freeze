import contextlib
import datetime
import functools
import logging
import io
import pickle
import re
import sys
import tempfile
import threading
import zlib
from pathlib import Path
import matplotlib.figure
import numpy
import pandas
from typing import Any, Generator, List, Mapping, Type, cast
from tqdm import tqdm

from charmonium.freeze import freeze
from charmonium.determ_hash import determ_hash


def insert_recurrence(lst: List[Any], idx: int) -> List[Any]:
    lst = lst.copy()
    lst.insert(idx, lst)
    return lst


class WithProperties:
    def __init__(self, value: int) -> None:
        self._attrib = value

    @property
    def attrib(self) -> int:
        raise RuntimeError("Shouldn't try to read attrib")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, WithProperties) and self._attrib == other._attrib


class WithGetFrozenState:
    def __init__(self, value: int) -> None:
        self._value = value

    def __getfrozenstate__(self) -> int:  # pylint: disable=no-self-use
        return 0


@functools.singledispatch
def single_dispatch_test(_obj: Any) -> Any:
    return _obj

@single_dispatch_test.register
def _(_obj: int) -> int:
    return _obj


def function_test(obj: int) -> int:
    return obj

def get_class(i: int) -> Type[Any]:
    class A:
        i: int = 0
        def foo(self) -> int:
            return self.i
    A.i = i
    return A


class ClassWithStaticMethod:
    @staticmethod
    def foo() -> int:
        return 1234
    @classmethod
    def bar(cls) -> int:
        return len(cls.__name__)
    def baz(self) -> int:
        return 3142 + self.bar()


global0 = 0
global1 = 1
readme_rpb = open("README.rst", "r+b")  # pylint: disable=consider-using-with
readme_rpb.seek(10)

def generator() -> Generator[int, None, None]:
    yield from range(10)

generator0 = generator()
generator1 = generator()
next(generator1)
context_manager = contextlib.contextmanager(generator)

range10p1 = iter(range(10))
next(range10p1)

# pylint: disable=consider-using-with
non_equivalents: Mapping[str, Any] = {
    "ellipses": [...],
    "bytearray": [bytearray(b"hello"), bytearray(b"world")],
    "tuple": [(), (1, 2)],
    "recursive_list": [
        insert_recurrence([1, 2, 3, 4], 2),
        insert_recurrence([1, 2, 3, 5], 2),
    ],
    "set": [{1, 2, 3}, {1, 2, 4}],
    "dict of dicts": [dict(a=1, b=2, c=3), dict(a=1, b=2, c=4)],
    "dict with diff order": [{"a": 1, "b": 2}, {"b": 2, "a": 1}],
    "memoryview": [memoryview(b"abc"), memoryview(b"def")],
    "@functools.singledispatch": [single_dispatch_test, determ_hash, freeze],
    "function": [cast, tqdm, *dir(tempfile)],
    "unbound methods": [ClassWithStaticMethod.foo, ClassWithStaticMethod.baz],
    "bound methods": [ClassWithStaticMethod.bar, ClassWithStaticMethod().baz],
    "lambda": [lambda: 1, lambda: 2, lambda: global0, lambda: global1],
    "builtin_function": [open, input],
    "code": [freeze.__code__, determ_hash.__code__],
    "module": [zlib, pickle],
    "range": [range(10), range(20)],
    "iterator": [iter(range(10)), range10p1],
    # TODO: make freeze work on generators
    # "generator": [generator0, generator1],
    "context manager": [context_manager],
    "logger": [logging.getLogger("a.b"), logging.getLogger("a.c")],
    "type": [List[int], List[float], ClassWithStaticMethod],
    "class": [WithProperties, WithGetFrozenState],
    "diff classes with same name": [get_class(3), get_class(4)],
    "obj of diff classes with the same name": [get_class(3)(), get_class(4)()],
    "instance method of diff classes with same name": [get_class(3)().foo, get_class(4)().foo],
    "io.BytesIO": [io.BytesIO(b"abc"), io.BytesIO(b"def")],
    "io.StringIO": [io.StringIO("abc"), io.StringIO("def")],
    "io.TextIOWrapper": [open("/tmp/test1", "w"), open("/tmp/test2", "w"), sys.stdout],
    "io.BufferedWriter": [
        open("/tmp/test3", "wb"),
        open("/tmp/test4", "wb"),
        sys.stdout.buffer,
    ],
    # `readme_rpb` already read 10 bytes, so it should be different than `open(...)`
    "io.BufferedRandom": [
        open("README.rst", "r+b"),  # pylint: disable=consider-using-with
        readme_rpb,
    ],
    "re.Pattern": [
        re.compile("abc"),
        re.compile("def"),
        re.compile("def", flags=re.MULTILINE),
    ],
    "matplotlib.figure.Figure": [matplotlib.figure.Figure()],
    # should have two distinct matches
    "re.Match": list(re.finditer("a", "abca")),
    "numpy numbers": [
        # floats should be different from ints of the same value
        numpy.int64(123),
        numpy.float32(123),
        numpy.int64(456),
        numpy.float32(456),
    ],
    "Path": [Path(), Path("abc"), Path("def")],
    "numpy.ndarray": [numpy.zeros(4), numpy.zeros(4, dtype=int), numpy.ones(4)],
    "obj with properties": [WithProperties(3), WithProperties(4)],
    "tqdm": [tqdm(range(10), disable=True)],
    "pandas.DataFrame": [
        pandas.DataFrame(data={"col1": [1, 2], "col2": [3, 4]}),
        pandas.DataFrame(data={"col1": [1, 3], "col2": [5, 4]}),  # change data
        pandas.DataFrame(data={"abc1": [1, 2], "abc2": [3, 4]}),  # change column names
        pandas.DataFrame(
            data={"col1": [1, 2], "col2": [3, 4]}, index=[45, 65]
        ),  # change index
    ],
    "functools.partial": [
        functools.partial(function_test, 3),
        functools.partial(function_test, 4),
    ],
    "datetime": [datetime.timedelta(days=3), datetime.timedelta(days=4)],
    "locky objects": [threading.Lock(), threading.RLock()],
}


non_copyable_types = {
    "module",
    "memoryview",
    "io.TextIOWrapper",
    "io.BufferedWriter",
    "io.BufferedRandom",
    "tqdm",
    "locky objects",
}


p = Path()
hash(p)
readme_rpb2 = open("README.rst", "r+b")  # pylint: disable=consider-using-with
readme_rpb2.read(10)
# pylint: disable=consider-using-with
equivalents: Mapping[str, List[Any]] = {
    "list": [[1, 2, 3], [1, 2, 3]],
    "Ellipsis": [..., ...],
    "recursive_list": [
        insert_recurrence([1, 2, 3, 4], 2),
        insert_recurrence([1, 2, 3, 4], 2),
    ],
    "lambda": [lambda: 1, lambda: 1],
    "obj with properties": [WithProperties(3), WithProperties(3)],
    "numpy.ndarray": [numpy.zeros(4), numpy.zeros(4)],
    "Path": [
        Path(),
        p,
        # when p gets hashed, the hash gets cached in an extra field.
    ],
    "diff identical class": [get_class(3), get_class(3)],
    "instances of diff identical classes": [get_class(3)(), get_class(3)()],
    "dict with same order": [{"a": 1, "b": 2}, {"a": 1, "b": 2}],
    "object with getfrozenstate": [WithGetFrozenState(3), WithGetFrozenState(4)],
    "logging.Logger": [logging.getLogger("a.b"), logging.getLogger("a.b")],
    "io.BytesIO": [io.BytesIO(b"abc"), io.BytesIO(b"abc")],
    "io.StringIO": [io.StringIO("abc"), io.StringIO("abc")],
    "io.TextIOWrapper": [open("/tmp/test5", "w"), open("/tmp/test5", "w")],
    "io.BufferedWriter": [open("/tmp/test6", "wb"), open("/tmp/test6", "wb")],
    # readme_rpb and readme_rpb2 are seeked to the same point
    "io.BufferedRandom": [readme_rpb, readme_rpb2],
    "pandas.DataFrame": [
        pandas.DataFrame(data={"col1": [1, 2], "col2": [3, 4]}),
        pandas.DataFrame(data={"col1": [1, 2], "col2": [3, 4]}),
    ],
    "functools.partial": [
        functools.partial(function_test, 3),
        functools.partial(function_test, 3),
    ],
    "threading.Lock": [threading.Lock(), threading.Lock()],
    "threading.RLock": [threading.RLock(), threading.RLock()],
}

# pylint: disable=consider-using-with
non_freezable_types: Mapping[str, Any] = {
    "io.BufferedReader": open("README.rst", "rb"),
    "io.TextIOBase": open("README.rst", "r"),
}
