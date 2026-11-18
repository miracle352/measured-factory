"""Examiner probes reuse the harness fixtures (world, build, web, corpus, page, ...)."""
import importlib.util
import os
import pathlib

_HERE = pathlib.Path(os.environ.get(
    "HARNESS_TESTS", "/home/iyanuoluwa/hack/sf-buildathon-2026/challenges/dossier/test"))
_spec = importlib.util.spec_from_file_location("harness_dossier_conftest", _HERE / "conftest.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
