from datetime import datetime

from django import template

register = template.Library()


@register.filter
def str_to_datetime(datetime_str):
    try:
        return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S.%f%z")
    except Exception as exc:
        print(exc)
        return datetime_str
