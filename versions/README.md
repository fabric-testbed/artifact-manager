# Versions

Version changes

## 1.0.0

First production release

### Changes

- revamp look / feel
- add My Artifacts landing page
- add view count, download count, and version count
- add double-blind options - show/hide authors and/or project reference
- split api_user into it's own app and modify primary key from UUID to INT

### Migrations

Artifact Manager data is backed up as an `artifacts.json` file which will need to be manually modified prior to the migration to the new version

- change `"model": "artifacts.apiuser"` to `"model": "apiuser.apiuser"` - moved apiuser to it's own app
    - for all `"model": "apiuser.apiuser"` entries, change `"pk"` to `"uuid"` - apiuser table now uses "id" as primary key
    - move `"uuid"` under the `"fields"` stanza
- change `"model": "artifacts.tasktimeouttracker"` to `"model": "apiuser.tasktimeouttracker"` - moved to apiuser app

## 0.9.0

Initial beta deployment
