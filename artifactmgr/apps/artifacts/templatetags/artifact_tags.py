import os
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


@register.filter
def project_url_from_uuid(project_uuid: str) -> Union[None, str]:
    if len(project_uuid) > 0:
        try:
            project_url = str(os.getenv('FABRIC_PORTAL')) + '/projects/' + project_uuid
        except Exception as exc:
            print(exc)
            return None
    else:
        return None
    return project_url


@register.filter
def project_url_from_uuid_anonymous(project_uuid: str) -> Union[None, str]:
    if len(project_uuid) > 0:
        try:
            project_url = str(os.getenv('FABRIC_PORTAL')) + '/experiments/public-projects/' + project_uuid
        except Exception as exc:
            print(exc)
            return None
    else:
        return None
    return project_url
