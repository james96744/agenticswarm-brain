from __future__ import annotations

try:
    from anatomy_wrapper import dispatch
except ModuleNotFoundError:
    from scripts.anatomy_wrapper import dispatch


if __name__ == "__main__":
    raise SystemExit(dispatch("cerebellum"))
