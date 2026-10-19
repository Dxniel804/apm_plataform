"""The access key of a NF-e: 44 digits, the last one a check digit (modulo 11, weights 2 to 9 from
the right). A typo is caught here, before the key becomes the proof of an expense."""

import re

_KEY = re.compile(r"^[0-9]{44}$")


def normalize(value: str) -> str:
    """The key as the NF-e prints it, in groups of four with spaces, becomes 44 digits."""
    return re.sub(r"[\s.\-]", "", value)


def check_digit(first43: str) -> int:
    total = 0
    weight = 2
    for digit in reversed(first43):
        total += int(digit) * weight
        weight = 2 if weight == 9 else weight + 1
    rest = total % 11
    return 0 if rest in (0, 1) else 11 - rest


def is_valid_key(key: str) -> bool:
    return _KEY.fullmatch(key) is not None and check_digit(key[:43]) == int(key[43])
