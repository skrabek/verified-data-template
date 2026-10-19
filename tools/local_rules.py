"""Rules specific to this project. validate.py calls check() after its own checks.

Add checks your domain needs, for example allowed predicates, value formats, or which
source classes may support which predicates. Return (errors, warnings) as lists of strings.
"""


def check(ctx):
    errors, warnings = [], []
    allowed = set(ctx["config"].get("predicates", []))
    if not allowed:
        return errors, warnings
    for identity, revisions in ctx["records"].items():
        data = revisions[-1]["doc"].get("data") or {}
        predicate = (data.get("proposition") or {}).get("predicate")
        if predicate and predicate not in allowed:
            errors.append(f"{identity}: predicate '{predicate}' is not listed in project.json")
    return errors, warnings
