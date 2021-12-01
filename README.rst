=================
charmonium.freeze
=================

.. image: https://img.shields.io/pypi/dm/charmonium.freeze
   :alt: PyPI Downloads
.. image: https://img.shields.io/pypi/l/charmonium.freeze
   :alt: PyPI Downloads
.. image: https://img.shields.io/pypi/pyversions/charmonium.freeze
   :alt: Python versions
.. image: https://img.shields.io/github/stars/charmoniumQ/charmonium.freeze?style=social
   :alt: GitHub stars
.. image: https://img.shields.io/librariesio/sourcerank/pypi/charmonium.freeze
   :alt: libraries.io sourcerank

- `PyPI`_
- `GitHub`_

Injectively, deterministically maps objects to hashable, immutable objects.

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
(1, 2, 3, frozenset({4, 5, 6}), ((('__newobj__', ('cls', 'args'), (None,), b'...'), (), ()), ('object',)))
>>> hash(frozen_obj) % 1
0

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

.. _`PyPI`: https://pypi.org/project/charmonium.freeze/
.. _`GitHub`: https://github.com/charmoniumQ/charmonium.freeze
.. _`pickle`: https://docs.python.org/3/library/pickle.html#pickling-class-instances
