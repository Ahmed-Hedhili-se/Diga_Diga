"""Odoo ERP connector. HireGuard is the secure AI layer in front of Odoo; Odoo stays the system of record.

Rules (docs/erp_odoo.md):
  1. ERP data is untrusted: every CV read from Odoo goes through `pipeline.service.process_cv`, like an upload.
  2. Writes to Odoo exist only as executor handlers (handlers.py). No route writes to Odoo.
  3. All or nothing: an Odoo failure during execution raises HTTP 502, the local transaction rolls back and the
     approval item stays `approved`, so it can be re-run.
  4. Least privilege: the Odoo bot user is Recruitment / Officer only and authenticates with an API key.
  5. No model-generated text reaches Odoo: notes are fixed templates, email bodies are HTML-escaped.
  6. Off by default (HG_ODOO_ENABLED=0): the app behaves exactly as without the connector.
  7. Reads may degrade (calendar falls back to plain slots); writes never do.
  8. ERP data is never used to train any model.
"""
