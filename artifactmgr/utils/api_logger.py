"""
Logger handles and the metrics event grammar for the FABRIC Artifact Manager.

This module is deliberately side effect free - it configures nothing. Every handler, formatter
and level lives in the ``LOGGING`` dictConfig in ``artifactmgr/server/settings.py``, which Django
applies during ``django.setup()`` in all entry paths (uWSGI, runserver, ``manage.py`` and the
management commands). Import the handles from here; do not call ``dictConfig`` anywhere else.

Two loggers
-----------
``consoleLogger``
    Operational output - errors, warnings and the occasional informational line. Goes to stdout,
    which uWSGI relays into ``docker compose logs django``. Use ``consoleLogger.exception(...)``
    inside an ``except`` block so the traceback survives, and %-style lazy arguments rather than
    f-strings, so the message is only formatted when the record is actually emitted::

        consoleLogger.exception('core_api: user lookup failed for %s', user_uuid)

``metricsLogger``
    The audit event stream. Goes to its own file (``METRICS_LOG_FILE``) and nowhere else: the
    logger sets ``propagate = False``, which is what keeps every audit record out of the
    operational stream. Do not call it directly - use :func:`metrics_event`, which enforces the
    grammar below.

Timestamps are UTC
------------------
Both streams timestamp in **UTC**, with milliseconds. ``settings.py`` sets
``logging.Formatter.converter = time.gmtime`` at module scope, so the conversion is already in
place when uWSGI pre-forks its workers and every worker inherits it.

Metrics line grammar
--------------------
A metrics line is::

    <Datetime> <Event message>

``<Datetime>`` comes from the formatter (UTC). ``<Event message>`` is::

    <Preamble> <subject> <verb> [<attr> '<value>'] [for <parent>] by usr:<uuid>

One preamble and one identifier prefix per entity - never two names for the same thing:

    ==================  ==================  ========================================
    Entity              Preamble            Identifier
    ==================  ==================  ========================================
    Artifact            ``Artifact event``  ``art:<uuid>``
    Artifact version    ``Version event``   ``ver:<uuid>``
    Artifact tag        ``Tag event``       ``tag:<tag>`` - a lower-cased string
                                            primary key, not a uuid
    Acting user         (never a subject)   ``usr:<uuid>``
    ==================  ==================  ========================================

The verb set is::

    create | modify | modify-add | modify-remove | delete | download

``modify`` records a scalar edit, ``modify-add`` / ``modify-remove`` a change to a many-to-many
relation, ``download`` a version bundle transfer.

Attribute values are quoted in exactly one style - ``<verb> <attr> '<value>'`` - and that style
is used everywhere. A literal single quote inside a value is escaped as ``\\'``. Identifiers are
the one exception: they are always bare, so ``modify-add author usr:<uuid>`` carries no quotes.
Wrap such a value with :func:`usr` rather than formatting it by hand.

``by usr:<uuid>`` is **mandatory on every event**. Every mutation in this service is
user-initiated and ``get_api_user()`` always returns an actor - falling back to the anonymous
``ApiUser`` - so an actor is never legitimately missing.

Identifiers are bare ``usr:<uuid>`` with **no email suffix**: the metrics stream carries no PII
by default. If an author email ever has to be recorded, it goes in an attribute value,
deliberately, and never in an identifier.

``delete`` means a **hard delete**. ``ArtifactViewSet.destroy()`` calls ``artifact.delete()``,
which removes the row and cascades to every ``ArtifactVersion``. The ``deleted`` / ``deleted_at``
model fields are vestigial and never written - there is no soft delete in this service,
whatever ``CLAUDE.md`` says.

Examples
--------
::

    Artifact event art:<uuid> create by usr:<uuid>
    Artifact event art:<uuid> modify title 'Deep packet inspection' by usr:<uuid>
    Artifact event art:<uuid> modify-add author usr:<uuid> by usr:<uuid>
    Artifact event art:<uuid> modify-remove tag 'ai-testbed' by usr:<uuid>
    Artifact event art:<uuid> delete by usr:<uuid>
    Version event ver:<uuid> create for art:<uuid> by usr:<uuid>
    Version event ver:<uuid> modify active 'False' by usr:<uuid>
    Version event ver:<uuid> download by usr:<uuid>
    Tag event tag:ai-testbed create by usr:<uuid>
    Tag event tag:ai-testbed modify restricted 'True' by usr:<uuid>
    Tag event tag:ai-testbed delete by usr:<uuid>
"""

import logging

__all__ = ['ARTIFACT', 'TAG', 'VERSION', 'consoleLogger', 'metricsLogger', 'metrics_event', 'usr']

# Operational stream - stdout, relayed by uWSGI into the container logs.
consoleLogger = logging.getLogger('consoleLogger')

# Audit stream - its own file, never propagated into the operational stream.
metricsLogger = logging.getLogger('metricsLogger')

# Entity preambles, and the identifier prefix each one uses. One of each, never mixed.
ARTIFACT = 'Artifact'
VERSION = 'Version'
TAG = 'Tag'

ENTITY_PREFIXES = {
    ARTIFACT: 'art',
    VERSION: 'ver',
    TAG: 'tag',
}

# The complete verb set. Anything else is a typo, and is reported on the console.
VERBS = ('create', 'modify', 'modify-add', 'modify-remove', 'delete', 'download')


class _Identifier(str):
    """A value that is itself an identifier, and so is emitted bare rather than quoted."""


def _one_line(value) -> str:
    """Render any value as a single line - no newlines, tabs, or runs of whitespace."""
    return ' '.join(('' if value is None else str(value)).split())


def _quoted(value) -> str:
    """Render an attribute value in the one quoting style the grammar allows: '<value>'."""
    if isinstance(value, _Identifier):
        return str(value)
    return "'" + _one_line(value).replace("'", "\\'") + "'"


def usr(user_uuid) -> _Identifier:
    """
    Wrap a user uuid as the bare identifier ``usr:<uuid>``.

    Use it whenever an attribute *value* names a user - the author added or removed by a
    ``modify-add`` / ``modify-remove`` event - so it is emitted unquoted, like every other
    identifier::

        metrics_event(ARTIFACT, artifact.uuid, 'modify-add', 'author', usr(author.uuid),
                      by=api_user.uuid)
    """
    return _Identifier('usr:' + _one_line(user_uuid))


def metrics_event(entity: str, subject, verb: str, attribute: str = None, value=None, *,
                  by=None, for_artifact=None) -> None:
    """
    Emit one audit line at INFO on ``metricsLogger``, in the grammar documented at the top of
    this module. Newlines and runs of whitespace are stripped from every part, so one event is
    always exactly one line.

    :param entity: ``ARTIFACT``, ``VERSION`` or ``TAG`` - supplies both the preamble and the
        identifier prefix.
    :param subject: identifier of the thing the event happened to (a uuid, or the tag string
        for ``TAG``).
    :param verb: one of :data:`VERBS`.
    :param attribute: the attribute name, for the ``modify`` family of verbs.
    :param value: the attribute value. Quoted as ``'<value>'`` unless wrapped with :func:`usr`.
    :param by: uuid of the acting user - mandatory on every event.
    :param for_artifact: uuid of the parent artifact, for ``VERSION`` events that need one.

    This never raises: an audit line must not be able to break the request that produced it.

    Call sites read as::

        metrics_event(ARTIFACT, artifact.uuid, 'create', by=api_user.uuid)
        metrics_event(ARTIFACT, artifact.uuid, 'modify', 'title', title, by=api_user.uuid)
        metrics_event(ARTIFACT, artifact.uuid, 'modify-add', 'author', usr(author.uuid),
                      by=api_user.uuid)
        metrics_event(ARTIFACT, artifact.uuid, 'modify-remove', 'tag', tag, by=api_user.uuid)
        metrics_event(ARTIFACT, artifact_uuid, 'delete', by=api_user.uuid)
        metrics_event(VERSION, version.uuid, 'create', for_artifact=artifact.uuid,
                      by=api_user.uuid)
        metrics_event(VERSION, version.uuid, 'modify', 'active', active, by=api_user.uuid)
        metrics_event(VERSION, version.uuid, 'download', by=api_user.uuid)
        metrics_event(TAG, tag, 'create', by=api_user.uuid)
        metrics_event(TAG, tag, 'modify', 'restricted', restricted, by=api_user.uuid)
        metrics_event(TAG, tag, 'delete', by=api_user.uuid)
    """
    try:
        prefix = ENTITY_PREFIXES.get(entity)
        if prefix is None:
            consoleLogger.warning('metrics_event: unknown entity %r, emitting it verbatim', entity)
            prefix = _one_line(entity).lower()
        if verb not in VERBS:
            consoleLogger.warning('metrics_event: unknown verb %r on a %s event', verb, entity)
        if not by:
            consoleLogger.error('metrics_event: no actor supplied for %r %r', entity, verb)

        parts = ['{0} event {1}:{2}'.format(_one_line(entity), prefix, _one_line(subject)),
                 _one_line(verb)]
        if attribute is not None:
            parts.append(_one_line(attribute))
        if value is not None:
            parts.append(_quoted(value))
        if for_artifact is not None:
            parts.append('for {0}:{1}'.format(ENTITY_PREFIXES[ARTIFACT], _one_line(for_artifact)))
        parts.append('by usr:{0}'.format(_one_line(by) if by else 'unknown'))

        metricsLogger.info(' '.join(parts))
    except Exception:  # an audit line must never break the request that produced it
        try:
            consoleLogger.exception('metrics_event: failed to emit a %r %r event', entity, verb)
        except Exception:
            pass
