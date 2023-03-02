==========================
charmonium.freeze
==========================

.. image:: https://img.shields.io/pypi/v/charmonium.freeze
   :alt: PyPI Package
   :target: https://pypi.org/project/charmonium.freeze
.. image:: https://img.shields.io/pypi/dm/charmonium.freeze
   :alt: PyPI Downloads
   :target: https://pypi.org/project/charmonium.freeze
.. image:: https://img.shields.io/pypi/l/charmonium.freeze
   :alt: License
   :target: https://github.com/charmoniumQ/charmonium.freeze/blob/main/LICENSE
.. image:: https://img.shields.io/pypi/pyversions/charmonium.freeze
   :alt: Python Versions
   :target: https://pypi.org/project/charmonium.freeze
.. image:: https://img.shields.io/librariesio/sourcerank/pypi/charmonium.freeze
   :alt: libraries.io sourcerank
   :target: https://libraries.io/pypi/charmonium.freeze
.. image:: https://img.shields.io/github/stars/charmoniumQ/charmonium.freeze?style=social
   :alt: GitHub stars
   :target: https://github.com/charmoniumQ/charmonium.freeze
.. image:: https://github.com/charmoniumQ/charmonium.freeze/actions/workflows/main.yaml/badge.svg
   :alt: CI status
   :target: https://github.com/charmoniumQ/charmonium.freeze/actions/workflows/main.yaml
.. image:: https://codecov.io/gh/charmoniumQ/charmonium.freeze/branch/main/graph/badge.svg?token=56A97FFTGZ
   :alt: Code Coverage
   :target: https://codecov.io/gh/charmoniumQ/charmonium.freeze
.. image:: https://img.shields.io/github/last-commit/charmoniumQ/charmonium.cache
   :alt: GitHub last commit
   :target: https://github.com/charmoniumQ/charmonium.freeze/commits
.. image:: http://www.mypy-lang.org/static/mypy_badge.svg
   :target: https://mypy.readthedocs.io/en/stable/
   :alt: Checked with Mypy
.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/psf/black
   :alt: Code style: black

Injectively, deterministically maps arbitrary objects to hashable, immutable values


----------
Quickstart
----------

If you don't have ``pip`` installed, see the `pip install guide`_.

.. _`pip install guide`: https://pip.pypa.io/en/latest/installing/

.. code-block:: console

    $ pip install charmonium.freeze

For a related project, |charmonium.cache|_, I needed a function that
deterministically, injectively maps objects to hashable objects.

- "Injectively" means ``freeze(a) == freeze(b)`` implies ``a == b``
  (with the precondition that ``a`` and ``b`` are of the same type).

- "Deterministically" means it should return the same value **across
  subsequent process invocations** (with the same interpreter major
  and minor version), unlike Python's |hash|_ function, which is not
  deterministic between processes.

- "Hashable" means one can call ``hash(...)`` on it. All hashable
  values are immutable.

.. |hash| replace:: ``hash``
.. _`hash`: https://docs.python.org/3.8/reference/datamodel.html#object.__hash__
.. |charmonium.cache| replace:: ``charmonium.cache``
.. _`charmonium.cache`: https://github.com/charmoniumQ/charmonium.cache

Have you ever felt like you wanted to "freeze" a list of arbitrary
data into a hashable value? Now you can.

>>> obj = [1, 2, 3, {4, 5, 6}, object()]
>>> hash(obj)
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
TypeError: unhashable type: 'list'

>>> from charmonium.freeze import freeze
>>> from pprint import pprint
>>> freeze(obj)
(1, 2, 3, frozenset({4, 5, 6}), (b'pickle', b'__newobj__', ((b'class', 'builtins.object'),)))

If you want to actually boil this down into a single integer, see
|charmonium.determ_hash|_. This library's job is just to freeze the
state.

.. |charmonium.determ_hash| replace:: ``charmonium.determ_hash``
.. _`charmonium.determ_hash`: https://github.com/charmoniumQ/charmonium.determ_hash

It even works on custom types.

>>> # Make a custom type
>>> class Struct:
...     def frobnicate(self):
...         print(123)
>>> s = Struct()
>>> s.attr = 4
>>> pprint(freeze(s))
(b'pickle',
 b'__newobj__',
 ((b'class',
   'Struct',
   (('frobnicate',
     (b'function',
      'frobnicate',
      b't\x00d\x01\x83\x01\x01\x00d\x00S\x00',
      (None, 123))),),
   b'class',
   'builtins.object'),),
 ('attr', 4))

And methods, functions, lambdas, etc.

>>> pprint(freeze(lambda x: x + 123))
(b'function', '<lambda>', b'|\x00d\x01\x17\x00S\x00', (None, 123))
>>> import functools
>>> pprint(freeze(functools.partial(print, 123)))
(b'pickle',
 b'class',
 'partial',
 ...,
 b'class',
 'builtins.object',
 ('builtin func', 'print'),
 ('builtin func', 'print'),
 (123,),
 (),
 None)
>>> pprint(freeze(Struct.frobnicate))
(b'function',
 'frobnicate',
 b't\x00d\x01\x83\x01\x01\x00d\x00S\x00',
 (None, 123))
>>> i = 0
>>> def square_plus_i(x):
...     # Value of global variable will be included in the function's frozen state.
...     return x**2 + i
... 
>>> pprint(freeze(square_plus_i))
(b'function',
 'square_plus_i',
 b'|\x00d\x01\x13\x00t\x00\x17\x00S\x00',
 (None, 2),
 ('i', 0))

If the source code of ``square_plus_i`` changes between successive invocations,
then the ``freeze`` value will change. This is useful for caching unchanged
functions.

-------------
Special cases
-------------

- ``freeze`` on functions returns their bytecode, constants, and
  closure-vars. The remarkable thing is that this is true across subsequent
  invocations of the same process. If the user edits the script and changes the
  function, then it's ``freeze`` will change too.

  ::

    (freeze(f) == freeze(g)) implies (for all x, f(x) == g(x))

- ``freeze`` on an object returns the data that used in the `pickle
  protocol`_. This makes ``freeze`` work correctly on most user-defined
  types. However, there can still be special cases: ``pickle`` may incorporate
  non-deterministic values. In this case, there are two remedies:

  - If you can tweak the definition of the class, add a method called
    ``__getfrozenstate__`` which returns a deterministic snapshot of the
    state. This takes precedence over the Pickle protocol, if it is defined.

    >>> class Struct:
    ...     pass
    >>> s = Struct()
    >>> s.attr = 4
    >>> pprint(freeze(s))
    (b'pickle',
     b'__newobj__',
     ((b'class', 'Struct', (), b'class', 'builtins.object'),),
     ('attr', 4))
    >>> # which is based on the Pickle protocol's definition of `__reduce__`:
    >>> pprint(s.__reduce__())
    (<function _reconstructor at 0x...>,
     (<class '__main__.Struct'>, <class 'object'>, None),
     {'attr': 4})


  - Otherwise, you can ignore certain attributes by creating a
    ``Config`` object or modifying the ``global_config`` object. See
    the source code of ``charmonium/freeze/config.py`` for more
    details.

    >>> from charmonium.freeze import freeze, Config
    >>> class Test:
    ...     deterministic_val = 3
    ...     nondeterministic_val = 4
    ... 
    >>> config = Config()
    >>> config.ignore_attributes.add(("__main__", "Test", "nondeterministic_val"))
    >>> freeze(Test(), config)
    (b'pickle', b'__newobj__', ((b'class', 'Test', (('deterministic_val', 3),), b'class', 'builtins.object'),))

    Note that ``nondeterministic_val`` is not present in the frozen object.


  - If you cannot tweak the definition of the class or monkeypatch a
    ``__getfrozenstate__`` method, you can still register `single dispatch
    handler`_ for that type:

    >>> from typing import Hashable, Optional, Dict, Tuple
    >>> from charmonium.freeze import _freeze_dispatch, _freeze
    >>> @_freeze_dispatch.register(Test)
    ... def _(
    ...         obj: Test,
    ...         config: Config,
    ...         tabu: Dict[int, Tuple[int, int]],
    ...         level: int,
    ...         index: int,
    ...     ) -> Tuple[Hashable, bool, Optional[int]]:
    ...     # Type annotations are optional.
    ...     # I have included them here for clarity.
    ... 
    ...     # `tabu` is for object cycle detection.
    ...     # It is handled for you.
    ... 
    ...     # `level` is for logging and recursion limits.
    ...     level = level + 1
    ... 
    ...     # Freeze should depend only on deterministic values.
    ...     if isinstance(obj.deterministic_val, int):
    ...         return (
    ...             obj.deterministic_val,
    ...             # The underlying frozen value. It should be hashable.
    ...             # It is usually made up of frozenset (replaces dict, set, and class attrs)
    ...             # and tuple (replaces list).
    ... 
    ...             False,
    ...             # Whether the obj is immutable
    ...             # If the obj is immutable, it's frozen value need not be recomputed every time.
    ...             # This is handled for you.
    ... 
    ...             None,
    ...             # The depth of references contained here or None
    ...             # Currently, this doesn't do anything.
    ...         )
    ...     else:
    ...         # If the underlying instance variable is not hashable, we can use recursion to help.
    ...         # Call `_freeze` instead of `freeze` to recurse with `tabu` and `level`.
    ...         return _freeze(obj.deterministic_val, tabu, level, 0)
    ... 
    >>> freeze(Test())
    3

- Note that as of Python 3.7, dictionaries "remember" their insertion order. As such,

  >>> freeze({"a": 1, "b": 2})
  (('a', 1), ('b', 2))
  >>> freeze({"b": 2, "a": 1})
  (('b', 2), ('a', 1))

  This behavior is controllable by ``Config.ignore_dict_order``, which emits a ``frozenset`` of pairs.

  >>> config = Config(ignore_dict_order=True)
  >>> freeze({"b": 2, "a": 1}, config) == freeze({"a": 1, "b": 2}, config)
  True

.. _`pickle protocol`: https://docs.python.org/3/library/pickle.html#pickling-class-instances
.. _`single dispatch handler`: https://docs.python.org/3/library/functools.html#functools.singledispatch

----------
Developing
----------

See `CONTRIBUTING.md`_ for instructions on setting up a development environment.

.. _`CONTRIBUTING.md`: https://github.com/charmoniumQ/charmonium.freeze/tree/main/CONTRIBUTING.md

---------
Debugging
---------

Use the following lines to see how ``freeze`` decomposes an object into
primitive values.

.. code:: python

    import logging, os
    logger = logging.getLogger("charmonium.freeze")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler("freeze.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    logger.debug("Program %d", os.getpid())

    i = 0
    def square_plus_i(x):
        # Value of global variable will be included in the function's frozen state.
        return x**2 + i

    from charmonium.freeze import freeze
    freeze(square_plus_i)


This produces a log such as in ``freeze.log``:

::

    freeze begin <function square_plus_i at 0x7f9228bff550>
     function <function square_plus_i at 0x7f9228bff550>
      tuple (('code', <code object square_plus_i at 0x7f9228c6cf50, file "/tmp/ipython_edit_303agyiz/ipython_edit_rez33yf_.py", line 2>), 'closure globals', {'i': 0})
       tuple ('code', <code object square_plus_i at 0x7f9228c6cf50, file "/tmp/ipython_edit_303agyiz/ipython_edit_rez33yf_.py", line 2>)
        'code'
        code <code object square_plus_i at 0x7f9228c6cf50, file "/tmp/ipython_edit_303agyiz/ipython_edit_rez33yf_.py", line 2>
         tuple (None, 2)
          None
          2
         b'|\x00d\x01\x13\x00t\x00\x17\x00S\x00'
       'closure globals'
       dict {'i': 0}
        'i'
        0
    freeze end

I do this to find the differences between subsequent runs:

.. code:: shell

    $ python code.py
    $ mv freeze.log freeze.0.log

    $ python code.py
    $ mv freeze.log freeze.1.log

    $ sed -i 's/at 0x[0-9a-f]*//g' freeze.*.log
    # This removes pointer values that appear in the `repr(...)`.

    $ meld freeze.0.log freeze.1.log
    # Alternatively, use `icdiff` or `diff -u1`.

TODO
----

- ☐ Correctness

  - ☑ Test hashing sets with different orders. Assert tests fail.
  - ☑ Test hashing dicts with different orders. Assert tests fail.
  - ☑ Don't include properties in hash.
  - ☑ Test that freeze of an object includes freeze of its instance methods.
  - ☑ Test functions with minor changes.
  - ☑ Test set/dict with diff hash.
  - ☑ Test obj with slots.
  - ☑ Test hash for objects and classes more carefully.
  - ☑ Improve test coverage.
  - ☑ Investigate when modules are assumed constant.
  - ☐ Detect if a module/package has a version. If present, use that. Else, use each attribute.
  - ☐ Support closures which include ``import x`` and ``from x import y``

- ☑ API

  - ☑ Use user-customizable multidispatch.
  - ☑ Bring hash into separate package.
  - ☑ Make it easier to register a freeze method for a type.
  - ☑ Encapsulate global config into object.
  - ☑ Make freeze object-oriented with a module-level instance, like ``random.random`` and ``random.Random``.
    - This makes it easier for different callers to have their own configuration options.
  - ☐ Add an option which returns a single 128-bit int instead of a structured object after a certain depth. This is what ``charmonium.determ_hash`` does. Use this configuration in ``charmonium.cache``.
  - ☐ Move "get call graph" into its own package.
  - ☐ Document configuration options.
  - ☐ Document ``summarize_diff`` and ``iterate_diffs``.
  - ☐ Have an API for ignoring modules in ``requirements.txt`` or ``pyproject.toml``, and just tracking them by version.
  - ☐ Config object should cascade with ``with config.set(a=b)``
  - ☐ Bring hash into the same package, by having ``config.hash_only``. When ``True``, we return a single int, else a representation of the original object.
    - I don't know. That makes it impossible to use the cache and memo. You don't know the hash of each thing.
  - ☐ Bring object-diff into separate package.xo

- ☑ Make ``freeze`` handle more types:

  - ☑ Module: freeze by name.
  - ☑ Objects: include the source-code of methods.
  - ☑ C extensions. freeze by name, like module
  - ☑ Methods
  - ☑ fastpath for numpy arrays
  - ☑ ``tqdm``
  - ☑ ``numpy.int64(1234)``
  - ☑ Pandas dataframe
  - ☑ Catch Pickle TypeError
  - ☑ Catch Pickle ImportError

- ☐ Performance

  - ☑ Memoize the hash of immutable data:
    - If function contains no locals or globals except other immutables, it is immutable.
    - If a collection is immutable and contains only immutables, it is immutable.
  - ☐ Consider deprecating ``combine_frozen``.
  - ☑ Make performance benchmarks.
