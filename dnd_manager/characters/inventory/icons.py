from pathlib import Path


def interface_asset_path(root, asset_path):
    reject_nested_asset(asset_path)
    candidate = (Path(root).resolve() / asset_path).resolve()
    require_png_asset(Path(root).resolve(), candidate)
    return candidate


def reject_nested_asset(asset_path):
    if "/" in asset_path or "\\" in asset_path:
        raise ValueError("Ressource invalide.")


def require_png_asset(root, candidate):
    if root not in candidate.parents or not candidate.is_file():
        raise ValueError("Ressource invalide.")
    if candidate.suffix.lower() != ".png":
        raise ValueError("Ressource invalide.")


def icon_page(root, directories, page, per_page=200):
    paths = sorted(icon_paths(root, directories))
    start = page * per_page
    selected = paths[start:start + per_page]
    next_page = page + 1 if start + per_page < len(paths) else None
    return selected, next_page


def icon_paths(root, directories):
    root = Path(root)
    return (path.relative_to(root).as_posix() for directory in directories
            for path in (root / directory).iterdir() if supported_image(path))


def supported_image(path):
    return path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}


def page_number(value):
    try:
        return max(0, int(value))
    except ValueError as error:
        raise ValueError("Page invalide.") from error
