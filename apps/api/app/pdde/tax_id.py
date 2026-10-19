"""The CNPJ (14 digits) and the CPF (11 digits) with their check digits: a typo is caught before the
number is printed on an official form. Only the digits are kept."""

import re


def normalize(value: str) -> str:
    return re.sub(r"[\s.\-/]", "", value)


def _digit(numbers: str, weights: list[int]) -> int:
    rest = sum(int(n) * w for n, w in zip(numbers, weights, strict=True)) % 11
    return 0 if rest < 2 else 11 - rest


def is_valid_cpf(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{11}", value) or len(set(value)) == 1:
        return False
    first = _digit(value[:9], list(range(10, 1, -1)))
    second = _digit(value[:10], list(range(11, 1, -1)))
    return value[9:] == f"{first}{second}"


def is_valid_cnpj(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{14}", value) or len(set(value)) == 1:
        return False
    first = _digit(value[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = _digit(value[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return value[12:] == f"{first}{second}"


def is_valid(value: str) -> bool:
    return is_valid_cnpj(value) if len(value) == 14 else is_valid_cpf(value)


def mask(value: str | None) -> str:
    """For the paper: 00.000.000/0000-00 or 000.000.000-00; anything else as it is."""
    if value is None:
        return ""
    if len(value) == 14:
        return f"{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}"
    if len(value) == 11:
        return f"{value[:3]}.{value[3:6]}.{value[6:9]}-{value[9:]}"
    return value
