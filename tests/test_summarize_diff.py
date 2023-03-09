from typing import Any

from charmonium.freeze import Config
from charmonium.freeze import ObjectLocation as OL
from charmonium.freeze import freeze
from charmonium.freeze import iterate_diffs_of_frozen as idof
from charmonium.freeze import summarize_diffs as sdof

config = Config(ignore_dict_order=True, use_hash=False)
frozen_obj0 = freeze([0, 1, 2, {3, 4}, {"a": 5, "b": 6, "c": 7}, 8], config)
frozen_obj1 = freeze([0, 8, 2, {3, 5}, {"a": 5, "b": 7, "d": 8}], config)


def test_iterate_diffs_of_frozen() -> None:
    differences = list(idof(frozen_obj0, frozen_obj1))
    assert differences[0][0].labels == ("obj0", ".__len__()")
    assert differences[1][0].labels == ("obj0", "[1]")
    assert differences[2][0].labels == ("obj0", "[3]", ".has()")
    assert differences[3][0].labels == ("obj0", "[3]", ".has()")
    assert differences[4][0].labels == ("obj0", "[4]", ".keys()", ".has()")
    assert differences[5][0].labels == ("obj0", "[4]", ".keys()", ".has()")
    assert differences[6][0].labels == ("obj0", "[4]", "['b']")
    assert len(differences) == 7


def test_summarize_diff() -> None:
    assert sdof(frozen_obj0, frozen_obj1).split("\n") == [
        "let obj0_sub = obj0",
        "let obj1_sub = obj1",
        "obj0_sub.__len__() == 6",
        "obj1_sub.__len__() == 5",
        "obj0_sub[1] == 1",
        "obj1_sub[1] == 8",
        "obj0_sub[3].has() == 4",
        "obj1_sub[3].has() == no such element",
        "obj0_sub[3].has() == no such element",
        "obj1_sub[3].has() == 5",
        "obj0_sub[4].keys().has() == c",
        "obj1_sub[4].keys().has() == no such element",
        "obj0_sub[4].keys().has() == no such element",
        "obj1_sub[4].keys().has() == d",
        "obj0_sub[4]['b'] == 6",
        "obj1_sub[4]['b'] == 7",
    ]


def test_summarize_diff_recursive() -> None:
    class Struct:
        child: Any

    a0 = Struct()
    a0.child = Struct()
    a0.child.child = a0
    a1 = Struct()
    a1.child = Struct()
    a1.child.child = a1.child
    assert len(list(idof(OL.create(0, freeze(a0)), OL.create(1, freeze(a1))))) == 1
    assert not list(idof(frozenset({}), frozenset({})))
