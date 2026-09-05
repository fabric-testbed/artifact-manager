import os
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand, CommandError

from artifactmgr.apps.apiuser.models import ApiUser
from artifactmgr.utils.api_logger import consoleLogger


def init_anon_api_user():
    """
    Initialize/Update the anonymous API User database entry
    """
    try:
        # check if anonymous API User exists
        api_user = ApiUser.objects.filter(uuid=os.getenv('API_USER_ANON_UUID')).first()
        if not api_user:
            # create Anonymous API User
            api_user = ApiUser(
                access_expires=datetime.now(timezone.utc) + timedelta(
                    minutes=int(os.getenv('API_USER_REFRESH_CHECK_MINUTES'))),
                access_type='cookie',
                affiliation='None',
                cilogon_id='None',
                email='None',
                fabric_roles=[],
                name=os.getenv('API_USER_ANON_NAME'),
                projects=[],
                uuid=os.getenv('API_USER_ANON_UUID')
            )
            api_user.save()
        else:
            # Anonymous API User already exists
            pass
    except Exception as exc:
        consoleLogger.exception('init_anon_api_user: could not initialize the anonymous API user')


class Command(BaseCommand):
    help = 'Initialize/Update the TaskTimeoutTracker table'

    def handle(self, *args, **kwargs):
        try:
            init_anon_api_user()

        except Exception as e:
            consoleLogger.exception('init_anon_api_user: initialization failed')
            raise CommandError('Initialization failed.')
