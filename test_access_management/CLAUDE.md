# test_access_management

Complete reference build of `access_management` (all 5 phases), kept separate so the user can test the finished feature set while building `access_management` step by step. Do not edit `access_management` from here.

- Models are prefixed `test.access.*` and tables `test_access_*` so both modules can be installed together. res.users gets `test_profile_ids` + computed `test_profile_line_ids`.
- Sync: `res.users._test_sync_profile_groups` + ledger `test.access.profile.grant`; triggers in profile/line/user create, write, unlink.
- Export: `controllers/main.py` route `/test_access_management/export/<profile|user>/<id>` using `utils/xlsx_io.py`.
- Upload: `wizard/profile_upload.py` (collect all errors with row/column, save nothing on error, update by key Name+Model+Group).
- Odoo 20: Binary field value is a `BinaryValue`; use `.content` for raw bytes (no b64decode).
- Tests: `python odoo-bin -c odoo.conf -d <db> -i test_access_management --test-enable --test-tags /test_access_management --stop-after-init` (add `--db-filter` if db name does not match `^odoo20`). 13 tests pass.
