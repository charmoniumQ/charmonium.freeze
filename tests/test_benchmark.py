import copy
from typing import Any

import obj_test_cases
import pytest

import charmonium.freeze


@pytest.mark.parametrize("input_kind", obj_test_cases.benchmark_cases.keys())
@pytest.mark.benchmark(
    disable_gc=True,
)
def test_benchmark(input_kind: str, benchmark: Any) -> None:
    config = copy.deepcopy(charmonium.freeze.global_config)
    config.use_hash = True
    config.memo.clear()
    # Warm the cache in config
    charmonium.freeze.freeze(obj_test_cases.benchmark_cases[input_kind], config)
    benchmark.pedantic(
        charmonium.freeze.freeze,
        args=(obj_test_cases.benchmark_cases[input_kind], config),
    )
