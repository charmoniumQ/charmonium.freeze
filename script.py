#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import datetime
import itertools
import os
import shlex
import shutil
import subprocess
import sys
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Awaitable,
    Callable,
    Iterable,
    List,
    Mapping,
    Optional,
    TypeVar,
    Union,
    cast,
)

# import autoimport
import setuptools
import tomllib
import typer
from charmonium.async_subprocess import run
from termcolor import cprint
from typing_extensions import ParamSpec

Params = ParamSpec("Parms")
Return = TypeVar("Return")


def coroutine_to_function(
    coroutine: Callable[Params, Awaitable[Return]]  # type: ignore
) -> Callable[Params, Return]:  # type: ignore
    @wraps(coroutine)
    def wrapper(*args: Params.args, **kwargs: Params.kwargs) -> Return:  # type: ignore
        return asyncio.run(coroutine(*args, **kwargs))  # type: ignore

    return wrapper


if TYPE_CHECKING:
    CompletedProc = subprocess.CompletedProcess[str]
else:
    CompletedProc = object


def default_checker(proc: CompletedProc) -> bool:
    return proc.returncode == 0


async def pretty_run(
    cmd: List[Union[Path, str]],
    checker: Callable[[CompletedProc], bool] = default_checker,
    env_override: Optional[Mapping[str, str]] = None,
) -> CompletedProc:
    start = datetime.datetime.now()
    proc = await run(
        cmd, capture_output=True, text=True, check=False, env_override=env_override
    )
    proc = cast(CompletedProc, proc)
    stop = datetime.datetime.now()
    delta = stop - start
    success = checker(proc)
    color = "green" if success else "red"
    if sys.version_info >= (3, 8):
        cmd_str = shlex.join(map(str, cmd))
    else:
        cmd_str = " ".join(map(str, cmd))
    cprint(
        f"$ {cmd_str}\nexited with status {proc.returncode} in {delta.total_seconds():.1f}s",
        color,
    )
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
    if not success:
        raise typer.Exit(code=1)
    return proc


def most_recent_common_ancestor(packages: List[str]) -> str:
    common_ancestor = packages[0].split(".")
    for package in packages:
        new_common_ancestor = []
        for seg1, seg2 in zip(common_ancestor, package.split(".")):
            if seg1 != seg2:
                break
            new_common_ancestor.append(seg1)
        common_ancestor = new_common_ancestor
    return ".".join(common_ancestor)


def get_package_path(package: str) -> Path:
    return Path().joinpath(*package.split("."))


app = typer.Typer()
tests_dir = Path("tests")
pyproject = tomllib.loads(Path("pyproject.toml").read_text())
extra_packages = [
    obj["include"] for obj in pyproject["tool"]["poetry"].get("packages", [])
]
src_packages = setuptools.find_packages() + extra_packages
main_package = most_recent_common_ancestor(src_packages)
assert main_package, f"No common ancestor of {src_packages}"
main_package_dir = get_package_path(main_package)
docsrc_dir = Path("docsrc")
build_dir = Path("build")
all_python_files = list(
    {
        *tests_dir.rglob("*.py"),
        *main_package_dir.rglob("*.py"),
        Path("script.py"),
        # docsrc_dir / "conf.py",
    }
)


T1 = TypeVar("T1")
T2 = TypeVar("T2")


@app.command()
@coroutine_to_function
async def fmt(parallel: bool = True) -> None:
    await pretty_run(
        [
            "autoflake",
            "--in-place",
            "--recursive",
            "--remove-all-unused-imports",
            "--ignore-init-module-imports",
            ".",
        ]
    )
    await pretty_run(["isort", "--overwrite-in-place", "--color", "."])
    await pretty_run(["black", *all_python_files])


@app.command()
@coroutine_to_function
async def test() -> None:
    await asyncio.gather(
        pretty_run(
            [
                "autoflake",
                "--in-place",
                "--recursive",
                "--remove-all-unused-imports",
                "--ignore-init-module-imports",
                ".",
            ],
        ),
        pretty_run(
            [
                "mypy",
                # "dmypy",
                # "run",
                # "--",
                "--namespace-packages",
                "--package",
                main_package,
            ],
            env_override={"MYPY_FORCE_COLOR": "1"},
        ),
        pretty_run(
            [
                "mypy",
                "--namespace-packages",
                *tests_dir.rglob("*.py"),
            ],
            env_override={
                "MYPY_FORCE_COLOR": "1",
                "PYTHONPATH": "tests:" + os.environ.get("PYTHONPATH", ""),
            },
        ),
        # pretty_run(
        #     [
        #         "pylint",
        #         "-j",
        #         "0",
        #         "--output-format",
        #         "colorized",
        #         "--score=y",
        #         *all_python_files,
        #     ],
        #     # see https://pylint.pycqa.org/en/latest/user_guide/run.html#exit-codes
        #     checker=lambda proc: proc.returncode & (1 | 2) == 0,
        # ),
        pytest(use_coverage=True, show_slow=True),
        pretty_run(
            [
                "radon",
                "cc",
                "--min",
                "c",
                "--show-complexity",
                "--no-assert",
                main_package_dir,
                tests_dir,
            ]
        ),
        pretty_run(
            [
                "radon",
                "mi",
                "--min",
                "b",
                "--show",
                "--sort",
                main_package_dir,
                tests_dir,
            ]
        ),
    )


@app.command()
@coroutine_to_function
async def per_env_tests() -> None:
    await asyncio.gather(
        pretty_run(
            # No daemon
            [
                "mypy",
                "--namespace-packages",
                "--package",
                main_package,
            ],
            env_override={"MYPY_FORCE_COLOR": "1"},
        ),
        pytest(use_coverage=False, show_slow=False),
    )


@app.command()
@coroutine_to_function
async def docs() -> None:
    await docs_inner()


async def docs_inner() -> None:
    if docsrc_dir.exists():
        await pretty_run(["sphinx-build", "-W", "-b", "html", docsrc_dir, "docs"])
    if docsrc_dir.exists():
        print(f"See docs in: file://{(Path() / 'docs' / 'index.html').resolve()}")


@app.command()
@coroutine_to_function
async def all_tests(interactive: bool = True) -> None:
    await all_tests_inner(interactive)


async def all_tests_inner(interactive: bool) -> None:
    dist = Path("dist")
    if dist.exists():
        shutil.rmtree(dist)
    # await pretty_run(["proselint", "README.rst"])
    await pretty_run(["rstcheck", "README.rst"])
    await pretty_run(["poetry", "build", "--quiet"])
    await pretty_run(["twine", "check", "--strict", *dist.iterdir()])
    shutil.rmtree(dist)

    # Tox already has its own parallelism,
    # and it shows a nice stateus spinner.
    # so I'll not `await pretty_run`
    subprocess.run(
        ["tox", "--parallel", "auto"],
        env={
            **os.environ,
            "PY_COLORS": "1",
            "TOX_PARALLEL_NO_SPINNER": "" if interactive else "1",
        },
        check=True,
    )


async def pytest(use_coverage: bool, show_slow: bool) -> None:
    if tests_dir.exists():
        await pretty_run(
            [
                "pytest",
                "--exitfirst",
                "--failed-first",
                *(["--durations=10"] if show_slow else []),
                *([f"--cov={main_package_dir!s}"] if use_coverage else []),
            ],
            checker=lambda proc: proc.returncode in {0, 5},
        )
        if use_coverage:
            await pretty_run(["coverage", "html"])
            report_dir = Path(pyproject["tool"]["coverage"]["html"]["directory"])
            print(
                f"See code coverage in: file://{(report_dir / 'index.html').resolve()}"
            )


class VersionPart(str, Enum):
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


T = TypeVar("T")


def flatten1(seq: Iterable[Iterable[T]]) -> Iterable[T]:
    return (item2 for item1 in seq for item2 in item1)


def dct_to_args(dct: Mapping[str, Union[bool, int, float, str]]) -> List[str]:
    def inner() -> Iterable[List[str]]:
        for key, val in dct.items():
            key = key.replace("_", "-")
            if isinstance(val, bool):
                modifier = "" if val else "no-"
                yield [f"--{modifier}{key}"]
            else:
                yield [f"--{key}", str(val)]

    return list(flatten1(inner()))


@app.command()
def publish(
    version_part: VersionPart,
    gen_docs: bool = True,
    bump: bool = True,
) -> None:
    if gen_docs:
        asyncio.run(docs_inner())
    if bump:
        subprocess.run(
            [
                "bump2version",
                *dct_to_args(pyproject["tool"]["bump2version"]),
                "--current-version",
                pyproject["tool"]["poetry"]["version"],
                version_part.value,
                "pyproject.toml",
                *itertools.chain.from_iterable(
                    Path(package.replace(".", "/")).glob("**/__init__.py")
                    for package in src_packages
                ),
            ],
            check=True,
        )
    extra_args = []
    if "TWINE_USERNAME" in os.environ:
        extra_args += ["--username", os.environ["TWINE_USERNAME"]]
    if "TWINE_PASSWORD" in os.environ:
        extra_args += ["--password", os.environ["TWINE_PASSWORD"]]
    try:
        subprocess.run(
            ["poetry", "publish", "--build", *extra_args],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        # Undo bump2version
        new_pyproject = tomllib.loads(Path("pyproject.toml").read_text())
        tag = "v" + new_pyproject["tool"]["bump2version"]["current_version"]
        subprocess.run(["git", "tag", "--delete", tag], check=True)
        subprocess.run(["git", "reset", "--hard", "HEAD~1"], check=True)
        shutil.rmtree("dist")
        raise e
    shutil.rmtree("dist")
    subprocess.run(["git", "push", "--tags"], check=True)
    subprocess.run(["git", "push"], check=True)
    # TODO: publish docs


if __name__ == "__main__":
    app()
