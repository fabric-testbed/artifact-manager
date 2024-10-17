"""
Migrate v0.9.0 to v1.0.0
- change `"model": "artifacts.apiuser"` to `"model": "apiuser.apiuser"` - moved apiuser to it's own app
    - for all `"model": "apiuser.apiuser"` entries, change `"pk"` to `"uuid"` - apiuser table now uses "id" as primary key
    - move `"uuid"` under the `"fields"` stanza
- change `"model": "artifacts.tasktimeouttracker"` to `"model": "apiuser.tasktimeouttracker"` - moved to apiuser app
"""
import json
from types import SimpleNamespace

INPUT_FILE = './input_files/artifacts-v0_9_0.json'
OUTPUT_FILE = './output_files/artifacts-v1_0_0.json'

input_obj = json.load(open(INPUT_FILE), object_hook=lambda d: SimpleNamespace(**d))
output_obj = []

for i in range(len(input_obj)):
    print(input_obj[i].model)
    input_obj_modified = False

    # modeL: artifacts:apiuser
    if input_obj[i].model == 'artifacts.apiuser':
        """
        {
            "model": "artifacts.apiuser",  <-- change to "apiuser.apiuser"
            "pk": "593dd0d3-cedb-4bc6-9522-a945da0a8a8e", <-- remove "pk" from here and insert under "fields" as "uuid"
            "fields": {
                "access_expires": "2024-08-29T19:52:51.310Z",
                "access_type": "cookie",
                "affiliation": "University of North Carolina at Chapel Hill",
                "cilogon_id": "http://cilogon.org/serverA/users/242181",
                "email": "stealey@unc.edu",
                "fabric_roles": "[\"Jupyterhub\", ..., \"long-lived-tokens\"]",
                "name": "Michael J. Stealey, Sr",
                "projects": "[\"74a5b28b-c1a2-4fad-882b-03362dddfa71\", ..., \"8b3a2eae-a0c0-475a-807b-e9af581ce4c0\"]"
            }
        }
        """
        item = input_obj[i]
        print('- INFO: Change model to "apiuser.apiuser"')
        item.model = 'apiuser.apiuser'
        print('- INFO: Change "pk" to "fields.uuid": {0}'.format(item.pk))
        item.fields.uuid = item.pk
        print('- INFO: Remove "pk"')
        del item.pk
        output_obj.append(item)
        input_obj_modified = True

    # model: artifacts:tasktimeouttrakcer
    if input_obj[i].model == 'artifacts.tasktimeouttracker':
        """
        {
            "model": "artifacts.tasktimeouttracker", <-- change to "apiuser.tasktimeouttracker"
            "pk": "047441d7-15d1-4ec1-bce0-e545a2de10c1",
            "fields": {
                "description": "Author Refresh Check",
                "last_updated": "2023-08-10T20:14:00.689Z",
                "name": "author_refresh_check",
                "timeout_in_seconds": 86400,
                "value": null
            }
        }
        """
        item = input_obj[i]
        print('- INFO: Change model to "apiuser.tasktimeouttracker"')
        item.model = 'apiuser.tasktimeouttracker'
        output_obj.append(item)
        input_obj_modified = True

    # everything else
    if not input_obj_modified:
        output_obj.append(input_obj[i])

print_obj = json.loads(json.dumps(output_obj, default=lambda s: vars(s)))
print(json.dumps(print_obj, indent=2))
with open(OUTPUT_FILE, 'w') as f:
    json.dump(print_obj, f, indent=2)
f.close()
