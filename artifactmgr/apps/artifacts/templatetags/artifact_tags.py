from datetime import timedelta, timezone
from typing import Union

from dateutil import parser
from django import template

register = template.Library()


@register.filter
def normalize_date_to_utc(date_str: str) -> Union[None, str]:
    if len(date_str) > 0:
        try:
            date_parsed = parser.parse(str(date_str)) + timedelta(milliseconds=100)
            date_parsed = date_parsed - timedelta(milliseconds=100)
            date_parsed = date_parsed.astimezone(timezone.utc)
        except Exception as exc:
            print(exc)
            return date_str
    else:
        return None
    return date_parsed
