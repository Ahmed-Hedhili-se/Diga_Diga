"""Every API route of the app, whatever the FastAPI version.

FastAPI 0.115 flattens included routers into `app.routes`. Newer releases keep each included router as one lazy
`_IncludedRouter`, so a test that walks `app.routes` for `APIRoute` sees none of the application's routes. This helper
gives both layouts the same shape: objects with the full `path`, `methods`, `dependant`, `name` and `endpoint`.
"""
from types import SimpleNamespace

from fastapi.routing import APIRoute


def api_routes(app) -> list:
    out = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            out.append(r)
        elif hasattr(r, "effective_route_contexts"):
            for ctx in r.effective_route_contexts():
                orig = ctx.original_route
                if isinstance(orig, APIRoute):
                    out.append(SimpleNamespace(path=ctx.path, methods=orig.methods, dependant=orig.dependant,
                                               name=orig.name, endpoint=orig.endpoint, route=orig))
    return out
