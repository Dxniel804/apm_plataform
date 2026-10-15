# ruff: noqa: E501  (statements)
"""Statements made by hand, in the two flavours of OFX, for the tests (no real data)."""

from datetime import date


def e2e(n: int) -> str:
    """An end-to-end id of a Pix: E and 31 digits."""
    return "E" + f"{n:031d}"


HEADER = "OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\nSECURITY:NONE\nENCODING:USASCII\nCHARSET:1252\nCOMPRESSION:NONE\nOLDFILEUID:NONE\nNEWFILEUID:NONE\n\n"


def sgml(
    lines: list[tuple[str, date, str, str]], start: date, end: date, balance: str | None = "1234.56"
) -> bytes:
    """OFX 1.x: the tags are never closed. Each line is (fitid, day, amount, memo)."""
    rows = "".join(
        f"<STMTTRN>\n<TRNTYPE>OTHER\n<DTPOSTED>{day:%Y%m%d}120000[-3:BRT]\n<TRNAMT>{amount}\n<FITID>{fitid}\n<MEMO>{memo}\n</STMTTRN>\n"
        for fitid, day, amount, memo in lines
    )
    ledger = (
        "" if balance is None else f"<LEDGERBAL><BALAMT>{balance}<DTASOF>{end:%Y%m%d}</LEDGERBAL>\n"
    )
    body = (
        "<OFX>\n<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS><DTSERVER>20261014120000<LANGUAGE>POR</SONRS></SIGNONMSGSRSV1>\n"
        "<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>\n"
        "<STMTRS><CURDEF>BRL<BANKACCTFROM><BANKID>001<ACCTID>12345-6<ACCTTYPE>CHECKING</BANKACCTFROM>\n"
        f"<BANKTRANLIST>\n<DTSTART>{start:%Y%m%d}\n<DTEND>{end:%Y%m%d}\n{rows}</BANKTRANLIST>\n{ledger}</STMTRS></STMTTRNRS></BANKMSGSRSV1>\n</OFX>\n"
    )
    return (HEADER + body).encode("cp1252")


def xml(lines: list[tuple[str, date, str, str]], start: date, end: date) -> bytes:
    """OFX 2.x: well formed XML."""
    rows = "".join(
        f"<STMTTRN><TRNTYPE>OTHER</TRNTYPE><DTPOSTED>{day:%Y%m%d}</DTPOSTED><TRNAMT>{amount}</TRNAMT><FITID>{fitid}</FITID><MEMO>{memo}</MEMO></STMTTRN>"
        for fitid, day, amount, memo in lines
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<?OFX OFXHEADER="200" VERSION="220" SECURITY="NONE"?>\n'
        f"<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST><DTSTART>{start:%Y%m%d}</DTSTART><DTEND>{end:%Y%m%d}</DTEND>{rows}</BANKTRANLIST>"
        "<LEDGERBAL><BALAMT>10.00</BALAMT></LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"
    ).encode()
