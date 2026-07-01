from importlib import import_module

_TARGET_MODULE = "material_agent.domain.scoring_engine"


def _domain_module():
    return import_module(_TARGET_MODULE)


def _public_names() -> list[str]:
    return sorted(name for name in vars(_domain_module()) if not name.startswith("_"))


def __getattr__(name: str):
    if name == "__all__":
        return _public_names()
    try:
        return getattr(_domain_module(), name)
    except AttributeError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_public_names()))
