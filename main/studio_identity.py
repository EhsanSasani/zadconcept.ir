"""Search ledger identifiers without treating invoice numbers as identity."""
from django.db.models import Q

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

def identity_query(value, prefix=""):
    value = str(value or "").translate(_DIGITS).strip()
    query = Q(**{f"{prefix}factor_code__icontains": value}) & ~Q(**{f"{prefix}production_type": "MISC"})
    identifier = value.upper().removeprefix("ST-")
    if identifier.isdecimal() and len(identifier) < 19:
        query |= Q(**{f"{prefix}pk": int(identifier)})
    return query
