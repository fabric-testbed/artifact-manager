from datetime import datetime, timedelta, timezone
from typing import Union

from dateutil import parser
from django import template

register = template.Library()


@register.filter
def str_to_datetime(datetime_str):
    try:
        return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S.%f%z")
    except Exception as exc:
        print(exc)
        return datetime_str


@register.filter
def normalize_date_to_utc(date_str: str) -> Union[None, str]:
    try:
        date_parsed = parser.parse(date_str) + timedelta(milliseconds=100)
        date_parsed = date_parsed - timedelta(milliseconds=100)
        date_parsed = date_parsed.astimezone(timezone.utc)
    except Exception as exc:
        print(exc)
        return date_str
    return date_parsed.strftime("%Y-%m-%d %H:%M:%S.%f%z")
