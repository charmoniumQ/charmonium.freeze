import re
import sys
from typing import List


class LineObj:
    def __init__(self, line_no, children) -> None:
        self.line_no = line_no
        self.children = children

    def __repr__(self) -> str:
        return f"LineObj({self.line_no}, {self.children})"


def get_line_lengths(lines: List[str], ignore_prefix: int = 0) -> List[int]:
    line_lengths = [0] * len(lines)

    stack = []
    for line_no, line in enumerate(lines):
        level = re.match(f"^ *", line[ignore_prefix:]).end()
        while level < len(stack):
            # terminate this block
            block = stack.pop()

            # pay our parent
            if stack:
                stack[-1].children += block.children

            # record this block
            line_lengths[block.line_no] = block.children
        while level + 1 > len(stack):
            # start a new block
            stack.append(LineObj(line_no, 0))
        if stack:
            stack[-1].children += 1

    while stack:
        block = stack.pop()
        if stack:
            stack[-1].children += block.children
        if block.line_no != -1:
            line_lengths[block.line_no] = block.children

    return line_lengths


test = [
    "  a",
    "a",
    "  a",
    "    a",
    "a",
    "a",
]
test_result = [1, 3, 2, 1, 1, 1]
assert get_line_lengths(test) == test_result, get_line_lengths(test)

if __name__ == "__main__":
    """
    # Run tests
    pytest --exitfirst > log

    # Trim pytest output
    cut --bytes=38- log > tmp

    # Annotate log with descendent counts
    python utils/annotate_logs.py < tmp > log2

    # Get the descendent counts
    cut --field=1 --delimiter=' ' log2 > tmp

    # Get top 30 counts
    sort --numeric --reverse | head --lines 30

    # all in one:
    pytest --exitfirst > log || (cut --bytes=38- log | python utils/annotate_logs.py > log2 && cut --field=1 --delimiter=' ' log2 | sort --numeric --reverse | head --lines 30)"""
    lines = list(sys.stdin)
    ignore_prefix = int(dict(enumerate(sys.argv)).get(1, 0))
    line_lengths = get_line_lengths(lines, ignore_prefix)
    for line, line_length in zip(lines, line_lengths):
        sys.stdout.write(f"{line_length: <6d}{line}")
