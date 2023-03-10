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
>>> freeze(obj)
9561766455304166758

-------------
Configuration
-------------

By changing the configuration, we can see the exact data that gets hashed.

We can change the configuration in a few ways:

- Object-oriented (preferred)

  >>> from charmonium.freeze import Config
  >>> freeze(obj, Config(use_hash=False))
  (1, 2, 3, frozenset({4, 5, 6}), ((('builtins', 'object'),), b'copyreg.__newobj__'))

- Global variable, but in this case, we must also clear the cache when we mutate
  the config.

  >>> from charmonium.freeze import global_config
  >>> global_config.use_hash = False
  >>> global_config.memo.clear()
  >>> freeze(obj)
  (1, 2, 3, frozenset({4, 5, 6}), ((('builtins', 'object'),), b'copyreg.__newobj__'))

``use_hash=True`` will be faster and produce less data, but I will demonstrate
it with ``use_hash=False`` so you can see what data gets included in the state.

See the source code ``charmonium/freeze/config.py`` for other configuration
options.

------------------
Freezing Functions
------------------

``freeze`` on functions returns their bytecode, constants, and closure-vars. The
remarkable thing is that this is true across subsequent invocations of the same
process. If the user edits the script and changes the function, then it's
``freeze`` will change too. This tells you if it is safe to use the cached value
of the function.

  ::

    (freeze(f) == freeze(g)) implies (for all x, f(x) == g(x))

>>> from pprint import pprint
>>> i = 456
>>> func = lambda x: x + i + 123
>>> pprint(freeze(func))
(('<lambda>', None, 123, b'|\x00t\x00\x17\x00d\x01\x17\x00S\x00'),
 (('i', 456),))

As promised, the frozen value includes the bytecode (``b'|x00t...``), the
constants (123), and the closure variables (456). When we change ``i``, we get a
different frozen value, indicating that the ``func`` might not be
computationally equivalent to what it was before.

>>> i = 789
>>> pprint(freeze(func))
(('<lambda>', None, 123, b'|\x00t\x00\x17\x00d\x01\x17\x00S\x00'),
 (('i', 789),))

``freeze`` works for objects that use function as data.

>>> import functools
>>> pprint(freeze(functools.partial(print, 123)))
(('print',),
 ('print', (123,), (), None),
 (frozenset({'partial',
             (...,
              ('args', (b'member_descriptor', b'args')),
              ('func', (b'member_descriptor', b'func')),
              ('keywords', (b'member_descriptor', b'keywords')))}),
  ('builtins', 'object')))

``freeze`` works for methods.

>>> class Greeter:
...     def __init__(self, greeting):
...         self.greeting = greeting
...     def greet(self, name):
...         print(self.greeting + " " + name)
... 
>>> pprint(freeze(Greeter.greet))
(('greet',
  None,
  ' ',
  b't\x00|\x00j\x01d\x01\x17\x00|\x01\x17\x00\x83\x01\x01\x00d\x00S\x00'),)

----------------
Freezing Objects
----------------

``freeze`` works on objects by freezing their state and freezing their
methods. The state is found by the `pickle protocol`_, which the Python language
implements by default for all classes. To get an idea of what this returns, call
``obj.__reduce_ex__(4)``. Because we reuse an existing protocol, ``freeze`` work
correctly on most user-defined types.

.. _`pickle protocol`: https://docs.python.org/3/library/pickle.html#pickling-class-instances

>>> s = Greeter("hello")
>>> pprint(s.__reduce_ex__(4))
(<function __newobj__ at 0x...>,
 (<class '__main__.Greeter'>,),
 {'greeting': 'hello'},
 None,
 None)
>>> pprint(freeze(s))
(((frozenset({'Greeter',
              (('__init__',
                (('__init__', None, b'|\x01|\x00_\x00d\x00S\x00'),)),
               ('greet',
                (('greet',
                  None,
                  ' ',
                  b't\x00|\x00j\x01d\x01\x17\x00|\x01\x17\x00\x83\x01'
                  b'\x01\x00d\x00S\x00'),)))}),
   ('builtins', 'object')),),
 (('greeting', 'hello'),),
 b'copyreg.__newobj__')

However, there can still be special cases: ``pickle`` may incorporate
non-deterministic values. In this case, there are three remedies:

- If you can tweak the definition of the class, add a method called
  ``__getfrozenstate__`` which returns a deterministic snapshot of the
  state. This takes precedence over the Pickle protocol, if it is defined.

  >>> class Greeter:
  ...     def __init__(self, greeting):
  ...         self.greeting = greeting
  ...     def greet(self, name):
  ...         print(self.greeting + " " + name)
  ...     def __getfrozenstate__(self):
  ...         return self.greeting
  ... 
  >>> pprint(freeze(Greeter("hello")))
  ((frozenset({'Greeter',
               (('__getfrozenstate__',
                 (('__getfrozenstate__', None, b'|\x00j\x00S\x00'),)),
                ('__init__', (('__init__', None, b'|\x01|\x00_\x00d\x00S\x00'),)),
                ('greet',
                 (('greet',
                   None,
                   ' ',
                   b't\x00|\x00j\x01d\x01\x17\x00|\x01\x17\x00\x83\x01'
                   b'\x01\x00d\x00S\x00'),)))}),
    ('builtins', 'object')),
   'hello')

- Otherwise, you can ignore certain attributes by changing the
  configuration. See the source code of ``charmonium/freeze/config.py`` for more
  details.

  >>> class Greeter:
  ...     def __init__(self, greeting):
  ...         self.greeting = greeting
  ...     def greet(self, name):
  ...         print(self.greeting + " " + name)
  ... 
  >>> config = Config(use_hash=False)
  >>> config.ignore_attributes.add(("__main__", "Greeter", "greeting"))
  >>> pprint(freeze(Greeter("hello"), config))
  (((frozenset({'Greeter',
                (('__init__',
                  (('__init__', None, b'|\x01|\x00_\x00d\x00S\x00'),)),
                 ('greet',
                  (('greet',
                    None,
                    ' ',
                    b't\x00|\x00j\x01d\x01\x17\x00|\x01\x17\x00\x83\x01'
                    b'\x01\x00d\x00S\x00'),)))}),
     ('builtins', 'object')),),
   (),
   b'copyreg.__newobj__')

  Note that ``'hello'`` is not present in the frozen object any more.

- If you cannot tweak the definition of the class or monkeypatch a
  ``__getfrozenstate__`` method, you can still register `single dispatch
  handler`_ for that type:

  .. _`single dispatch handler`: https://docs.python.org/3/library/functools.html#functools.singledispatch

  >>> from typing import Hashable, Optional, Dict, Tuple
  >>> from charmonium.freeze import _freeze_dispatch, _freeze
  >>> @_freeze_dispatch.register(Greeter)
  ... def _(
  ...         obj: Greeter,
  ...         config: Config,
  ...         tabu: Dict[int, Tuple[int, int]],
  ...         level: int,
  ...         index: int,
  ...     ) -> Tuple[Hashable, bool, Optional[int]]:
  ...     # Type annotations are optional.
  ...     # I have included them here for clarity.
  ... 
  ...     # `tabu` is for object cycle detection. It is handled for you.
  ...     # `level` is for logging and recursion limits. It is incremented for you.
  ...     # `index` is the "birth order" of the children.
  ...     frozen_greeting = _freeze(obj.greeting, config, tabu, level, 0)
  ... 
  ...     return (
  ...         frozen_greeting[0],
  ...         # Remember that _freeze returns a triple;
  ...         # we are only interested in the first element here.
  ... 
  ...         False,
  ...         # Whether the obj is immutable
  ...         # If the obj is immutable, it's frozen value need not be recomputed every time.
  ...         # This is handled for you.
  ... 
  ...         None,
  ...         # The depth of references contained here or None
  ...         # Currently, this doesn't do anything.
  ...     )
  ... 
  >>> freeze(Greeter("Hello"))
  'Hello'

----------------
Dictionary order
----------------

As of Python 3.7, dictionaries "remember" their insertion order. As such,

>>> freeze({"a": 1, "b": 2})
(('a', 1), ('b', 2))
>>> freeze({"b": 2, "a": 1})
(('b', 2), ('a', 1))

This behavior is controllable by ``Config.ignore_dict_order``, which emits a ``frozenset`` of pairs.

>>> config = Config(ignore_dict_order=True)
>>> freeze({"b": 2, "a": 1}, config) == freeze({"a": 1, "b": 2}, config)
True

--------------
Summarize diff
--------------

This enables a pretty neat utility to compare two arbitrary Python objects.

>>> from charmonium.freeze import summarize_diffs
>>> obj0 = [0, 1, 2, {3, 4}, {"a": 5, "b": 6, "c": 7}, 8]
>>> obj1 = [0, 8, 2, {3, 5}, {"a": 5, "b": 7, "d": 8}]
>>> print(summarize_diffs(obj0, obj1))
let obj0_sub = obj0
let obj1_sub = obj1
obj0_sub.__len__() == 6
obj1_sub.__len__() == 5
obj0_sub[1] == 1
obj1_sub[1] == 8
obj0_sub[3].has() == 4
obj1_sub[3].has() == no such element
obj0_sub[3].has() == no such element
obj1_sub[3].has() == 5
obj0_sub[4].keys().has() == c
obj1_sub[4].keys().has() == no such element
obj0_sub[4].keys().has() == no such element
obj1_sub[4].keys().has() == d
obj0_sub[4]['b'] == 6
obj1_sub[4]['b'] == 7

And if you don't like my printing style, you can get a programatic
access to this information.

>>> from charmonium.freeze import iterate_diffs
>>> for o1, o2 in iterate_diffs(obj0, obj1):
...    print(o1, o2, sep="\n")
ObjectLocation(labels=('obj0', '.__len__()'), objects=(..., 6))
ObjectLocation(labels=('obj1', '.__len__()'), objects=(..., 5))
ObjectLocation(labels=('obj0', '[1]'), objects=(..., 1))
ObjectLocation(labels=('obj1', '[1]'), objects=(..., 8))
ObjectLocation(labels=('obj0', '[3]', '.has()'), objects=(...), 4))
ObjectLocation(labels=('obj1', '[3]', '.has()'), objects=(..., 'no such element'))
ObjectLocation(labels=('obj0', '[3]', '.has()'), objects=(...), 'no such element'))
ObjectLocation(labels=('obj1', '[3]', '.has()'), objects=(..., 5))
ObjectLocation(labels=('obj0', '[4]', '.keys()', '.has()'), objects=(..., 'c'))
ObjectLocation(labels=('obj1', '[4]', '.keys()', '.has()'), objects=(..., 'no such element'))
ObjectLocation(labels=('obj0', '[4]', '.keys()', '.has()'), objects=(..., 'no such element'))
ObjectLocation(labels=('obj1', '[4]', '.keys()', '.has()'), objects=(..., 'd'))
ObjectLocation(labels=('obj0', '[4]', "['b']"), objects=(..., 6))
ObjectLocation(labels=('obj1', '[4]', "['b']"), objects=(..., 7))


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

If ``freeze(obj)`` is taking a long time, try adding ``freeze(obj,
Config(recursion_limit=20))``. This causes an exception if ``freeze`` recurses
more than a certain number of times. If you hit this exception, consider adding
ignored class, functions, attributes, or objects in ``Config``.

----------
Developing
----------

See `CONTRIBUTING.md`_ for instructions on setting up a development environment.

.. _`CONTRIBUTING.md`: https://github.com/charmoniumQ/charmonium.freeze/tree/main/CONTRIBUTING.md


----
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
  - ☑ Add an option which returns a single 128-bit int instead of a structured object after a certain depth. This is what ``charmonium.determ_hash`` does. Use this configuration in ``charmonium.cache``.
  - ☐ Move "get call graph" into its own package.
  - ☐ Document configuration options.
  - ☑ Document ``summarize_diff`` and ``iterate_diffs``.
  - ☐ Have an API for ignoring modules in ``requirements.txt`` or ``pyproject.toml``, and just tracking them by version.
  - ☑ Config object should cascade with ``with config.set(a=b)``

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
  - ☑ Make performance benchmarks.
