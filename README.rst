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
   :target: https://github.com/charmonium/charmonium.freeze/blob/main/LICENSE
.. image:: https://img.shields.io/pypi/pyversions/charmonium.freeze
   :alt: Python Versions
   :target: https://pypi.org/project/charmonium.freeze
.. image:: https://img.shields.io/librariesio/sourcerank/pypi/charmonium.freeze
   :alt: libraries.io sourcerank
   :target: https://libraries.io/pypi/charmonium.freeze
.. image:: https://img.shields.io/github/stars/charmonium/charmonium.freeze?style=social
   :alt: GitHub stars
   :target: https://github.com/charmonium/charmonium.freeze
.. image:: https://github.com/charmonium/charmonium.freeze/actions/workflows/main.yaml/badge.svg
   :alt: CI status
   :target: https://github.com/charmonium/charmonium.freeze/actions/workflows/main.yaml
.. image:: https://img.shields.io/github/last-commit/charmoniumQ/charmonium.determ_hash
   :alt: GitHub last commit
   :target: https://github.com/charmonium/charmonium.freeze/commits
.. image:: http://www.mypy-lang.org/static/mypy_badge.svg
   :target: https://mypy.readthedocs.io/en/stable/
   :alt: Checked with Mypy
.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/psf/black
   :alt: Code style: black

Injectively, deterministically maps objects to hashable, immutable objects

``frozenset`` is to ``set`` as ``freeze`` is to ``Any``.

That is, ``type(a) is type(b) and a != b`` implies ``freeze(a) != freeze(b)``.

Moreover, this function is deterministic, so it can be used to compare
states **across subsequent process invocations** (with the same
interpreter major and minor version).

>>> obj = [1, 2, 3, {4, 5, 6}, object()]
>>> hash(obj)
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
TypeError: unhashable type: 'list'

>>> from charmonium.freeze import freeze
>>> frozen_obj = freeze(obj)
>>> frozen_obj
(1, 2, 3, frozenset({4, 5, 6}), ('args', 'object'))

It even works on custom types.

>>> # Make a custom type
>>> class Struct:
...     def frobnicate(self):
...         print(123)
>>> s = Struct()
>>> s.attr = 4
>>> freeze(s)
('args', 'Struct', 'state', (('attr', 4),))

And methods, functions, lambdas, etc.

>>> freeze(lambda x: x + 123)
(('code', (('name', '<lambda>'), ('varnames', ('x',)), ('constants', (None, 123)), ('bytecode', b'|\x00d\x01\x17\x00S\x00'))),)
>>> import functools
>>> freeze(functools.partial(print, 123))
('constructor', 'partial', 'args', 'print', 'state', ('print', (123,), (), None))
>>> freeze(Struct.frobnicate)
(('code', (('name', 'frobnicate'), ('varnames', ('self',)), ('constants', (None, 123)), ('bytecode', b't\x00d\x01\x83\x01\x01\x00d\x00S\x00'))),)

If the source code of ``Struct.frobnicate`` changes between successive
invocations, then the ``freeze`` value will change. This is useful for caching
unchanged functions.


-------------
Special cases
-------------

- ``freeze`` on functions returns their bytecode, constants, and
  closure-vars. This means that ``freeze_state(f) == freeze_state(g)`` implies
  ``f(x) == g(x)``. The remarkable thing is that this is true across subsequent
  invocations of the same process. If the user edits the script and changes the
  function, then it's ``freeze_state`` will change too.

- ``freeze`` on objects returns the objects that would be used by `pickle`_ from
  ``__reduce__``, ``__reduce_ex__``, ``__getnewargs__``, ``__getnewargs_ex__``,
  and ``__getstate__``. The simplest of these to customize your object
  ``__gestate__``. See the `pickle`_ documentation for details.

- In the cases where ``__getstate__`` is already defined for pickle, and this
  definition is not suitable for ``freeze_state``, one may override this with
  ``__getfrozenstate__`` which takes precedence.

Although, this function is not infallible for user-defined types; I will do my
best, but sometimes these laws will be violated. These cases include:

- Cases where ``__eq__`` makes objects equal despite differing attributes or
  inversely make objects inequal despite equal attributes.

   - This can be mitigated if ``__getstate__`` or ``__getfrozenstate__``

.. _`pickle`: https://docs.python.org/3/library/pickle.html#pickling-class-instances

------------
Installing
------------

If you don't have ``pip`` installed, see the `pip install guide`_.

.. _`pip install guide`: https://pip.pypa.io/en/latest/installing/

.. code-block:: console

    $ pip install charmonium.freeze

See `CONTRIBUTING.md`_ for instructions on setting up a development environment.

.. _`CONTRIBUTING.md`: https://github.com/charmonium/charmonium.freeze/tree/main/CONTRIBUTING.md

---------
Debugging
---------

Use the following lines to see how ``freeze`` decomposes an object. It shows the
object tree that ``freeze`` walks until it reaches primitive values on the
leaves.

.. code:: python

    import logging
    import os
    logger = logging.getLogger("charmonium.freeze")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler("freeze.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    logger.debug("Program %d", os.getpid())
