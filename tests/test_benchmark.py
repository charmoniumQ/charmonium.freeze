from typing import Any

import pytest
from charmonium.freeze import freeze
import obj_test_cases


@pytest.mark.parametrize("input_kind", obj_test_cases.benchmark_cases.keys())
@pytest.mark.benchmark(
    disable_gc=True,
)
def test_benchmark(input_kind: str, benchmark: Any) -> None:
    benchmark(freeze, obj_test_cases.benchmark_cases[input_kind])
