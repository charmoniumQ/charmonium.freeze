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
(1, 2, 3, frozenset({4, 5, 6}), ('object',))

It even works on custom types.

>>> # Make a custom type
>>> class Struct:
...     def frobnicate(self):
...         print(123)
>>> s = Struct()
>>> s.attr = 4
>>> freeze(s)
('Struct', (('attr', 4),))

And methods, functions, lambdas, etc.

>>> freeze(lambda x: x + 123)
(('<lambda>', ('x',), (None, 123), b'|\x00d\x01\x17\x00S\x00'), (), ())
>>> import functools
>>> freeze(functools.partial(print, 123))
('partial', 'print', ('print', (123,), (), None))
>>> freeze(Struct.frobnicate)
(('frobnicate', ('self',), (None, 123), b't\x00d\x01\x83\x01\x01\x00d\x00S\x00'), (), ())

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

.. _`PyPI`: https://pypi.org/project/charmonium.freeze/
.. _`GitHub`: https://github.com/charmoniumQ/charmonium.freeze
.. _`pickle`: https://docs.python.org/3/library/pickle.html#pickling-class-instances
