"""Jalali report input; database boundaries remain Gregorian dates."""
import re

import jdatetime


def parse_persian_date(value):
    value = value.strip().translate(str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    if not re.fullmatch(r"[0-9]{4}/[0-9]{1,2}/[0-9]{1,2}", value):
        raise ValueError("Expected a Jalali date in YYYY/MM/DD format")
    year, month, day = map(int, value.split("/"))
    return jdatetime.date(year, month, day).togregorian()


def format_persian_date(value):
    result = jdatetime.date.fromgregorian(date=value)
    return f"{result.year:04d}/{result.month:02d}/{result.day:02d}".translate(
        str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
