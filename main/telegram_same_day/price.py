"""Conservative whole-toman caption parser; never guess from arbitrary digits."""
import re
from decimal import Decimal

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
NUMBER = r"(?:[0-9]{1,3}(?:[,/٬،][0-9]{3})+|[0-9]+)"
PRICE_LINE = re.compile(rf"(?:قیمت\s*[:：]?\s*)?({NUMBER})\s*(?:تومان)?[\s.!]*")


class PriceError(ValueError):
    pass


def parse_price(caption):
    if not isinstance(caption, str) or len(caption) > 4096:
        raise PriceError("invalid_caption")
    text = caption.translate(DIGITS).replace("\u200c", " ")
    candidates = []
    for line in text.splitlines():
        line = line.strip()
        match = PRICE_LINE.fullmatch(line)
        if match:
            value = int(re.sub(r"[,/٬،]", "", match[1]))
            if not 0 < value <= 999_999_999_999:
                raise PriceError("price_out_of_range")
            candidates.append(value)
        elif "قیمت" in line or "تومان" in line or "ریال" in line:
            raise PriceError("ambiguous_price")
    if len(candidates) != 1:
        raise PriceError("missing_or_multiple_prices")
    return candidates[0]


# The confirmed group convention is thousands of toman for bare amounts <100000.
# Explicit تومان always means literal toman; t/ت are the team's shorthand.
GROUP_NUMBER = r"(?:[0-9]{1,3}(?:[,/٬،. ][0-9]{3})+|[0-9]+(?:[./٫][0-9]{1,6})?)"
GROUP_LABEL = r"(?:قیمت(?:\s+(?:فروش|نهایی))?|مبلغ|بها|فی)"
GROUP_LINE = re.compile(
    rf"(?:{GROUP_LABEL}\s*[:：=]?\s*)?(?P<number>{GROUP_NUMBER})\s*"
    r"(?P<scale>میلیون)?\s*(?P<unit>تومان|تومن|هزار(?:\s+تومان)?|میلیون(?:\s+تومان)?|ت|t|k|m)?[\s!]*",
    re.IGNORECASE,
)


def parse_group_price(text):
    if not isinstance(text, str) or len(text) > 4096:
        raise PriceError("invalid_caption")
    text = text.translate(DIGITS).translate(str.maketrans("يك", "یک")).replace("\u200c", " ")
    text = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", text)
    text = text.replace("تومن", "تومان")
    text = re.sub(r"(?<=\d)\s*([/٬،٫,.])\s*(?=\d)", r"\1", text)
    candidates = []
    for line in text.splitlines():
        line = line.strip().strip("💰💵💸🏷️: ")
        labels = list(re.finditer(GROUP_LABEL, line))
        if len(labels) == 1:
            prefix = line[:labels[0].start()]
            if not any(char.isdigit() for char in prefix):
                line = line[labels[0].start():]
        if re.fullmatch(rf"{GROUP_LABEL}\s*[:：=]?", line):
            continue  # A label alone may precede the amount on the next line.
        composite = re.fullmatch(
            rf"(?:{GROUP_LABEL}\s*[:：=]?\s*)?([1-9][0-9]*)\s*میلیون\s*و\s*"
            r"([0-9]{1,3})\s*هزار(?:\s*تومان)?[\s!]*", line,
        )
        if composite:
            value = int(composite[1]) * 1000000 + int(composite[2]) * 1000
            if value > 999999999999:
                raise PriceError("price_out_of_range")
            candidates.append(value)
            continue
        match = GROUP_LINE.fullmatch(line)
        if not match:
            if any(word in line for word in ("قیمت", "مبلغ", "بها", "تومان", "تومن", "ریال", "میلیون", "هزار")):
                raise PriceError("ambiguous_price")
            continue
        raw, unit = match["number"], (match["unit"] or "").lower()
        if re.match(r"0[0-9]", raw):
            raise PriceError("ambiguous_price")
        scale = match["scale"]
        # A decimal with an explicit million unit is unambiguous (2.680 million).
        million = bool(scale) or unit in {"میلیون", "میلیون تومان", "m"}
        if million and re.fullmatch(r"[0-9]+[./٫][0-9]+", raw):
            value = Decimal(raw.replace("٫", ".").replace("/", "."))
        elif re.fullmatch(r"[0-9]{1,3}(?:[,/٬،. ][0-9]{3})+", raw):
            value = Decimal(re.sub(r"[,/٬،. ]", "", raw))
        else:
            value = Decimal(raw.replace("٫", ".").replace("/", "."))
        if million:
            value *= 1000000
        elif unit in {"هزار", "هزار تومان", "k"}:
            value *= 1000
        elif unit not in {"تومان", "تومن"}:
            if value != value.to_integral_value() or (
                re.fullmatch(r"[0-9]+[./٫][0-9]+", raw)
                and not re.fullmatch(r"[0-9]{1,3}(?:[./][0-9]{3})+", raw)
            ):
                # Decimal shorthand 2.68 means 2.68 million in this group.
                value *= 1000000
            elif value < 100000:
                value *= 1000
        if value != value.to_integral_value() or not 0 < value <= 999999999999:
            raise PriceError("price_out_of_range")
        candidates.append(int(value))
    if len(candidates) != 1:
        raise PriceError("missing_or_multiple_prices")
    return candidates[0]
