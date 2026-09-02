"""core/system/version.py – Liest App- und Core-Metadaten aus app.yaml / core.yaml."""
from pathlib import Path


def _read_yaml(yaml_path: Path) -> dict:
    try:
        import yaml
        with open(yaml_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_app_version(app_root: Path, default: str = "—") -> str:
    try:
        from importlib.metadata import version
        name = str(_read_yaml(app_root / "app.yaml").get("name", ""))
        if name:
            return _clean_version(version(name))
    except Exception:
        pass
    return str(_read_yaml(app_root / "app.yaml").get("version", default))


def get_app_name(app_root: Path, default: str = "app") -> str:
    return str(_read_yaml(app_root / "app.yaml").get("name", default))


def get_display_name(app_root: Path, default: str = "App") -> str:
    return str(_read_yaml(app_root / "app.yaml").get("display_name", default))


def get_disabled_modules(app_root: Path) -> list[str]:
    """Core-Module (Keys, z.B. 'scheduler'), die diese App nicht laden will
    (app.yaml: disabled_modules) -- für Core-Module, die zum App-Zweck nicht
    passen (z.B. Scheduler bei rein ereignisgesteuerten Apps ohne
    Zeitplanung). Betrifft nur core/modules/, keine App-eigenen Module."""
    raw = _read_yaml(app_root / "app.yaml").get("disabled_modules", [])
    return [str(x) for x in raw] if raw else []


def get_auth_config(app_root: Path) -> dict:
    """Auth-Konfiguration aus app.yaml (Schlüssel `auth:`) -- opt-in pro App,
    siehe ui/app.py::create() und [[E-003]]. `enabled` schaltet die
    WebAuthn/Passkey-Login-Pflicht für die UI frei; rp_id/rp_name/origin
    sind Startwerte für die gleichnamigen Settings (später über die
    Settings-UI änderbar, ohne app.yaml erneut anzufassen)."""
    raw = _read_yaml(app_root / "app.yaml").get("auth", {}) or {}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "rp_id": str(raw.get("rp_id", "")),
        "rp_name": str(raw.get("rp_name", "")),
        "origin": str(raw.get("origin", "")),
        "exempt_prefixes": [str(x) for x in (raw.get("exempt_prefixes") or [])],
        # Default True (Rückwärtskompatibel) -- Apps ohne HTTPS brauchen das
        # Passwort weiterhin als einzigen nutzbaren Weg (Passkeys erfordern
        # einen sicheren Kontext). Apps mit HTTPS koennen es gezielt
        # abschalten, siehe system/auth.py-Docstring.
        "password_fallback": bool(raw.get("password_fallback", True)),
    }


def _clean_version(v: str) -> str:
    """Bereinigt Dev-Versionen:
    - Entfernt lokalen Hash-Teil (+g...)
    - Ersetzt bei Monatswechsel die Basis durch YY.NewMM.1
      z.B. '26.3.14.dev2' im April → '26.4.1.dev2'
    """
    from datetime import date
    v = v.split("+")[0]  # Hash entfernen
    if ".dev" not in v:
        return v
    base, dev = v.split(".dev", 1)
    parts = base.split(".")
    if len(parts) == 3:
        today = date.today()
        cur_yy, cur_mm = today.year % 100, today.month
        try:
            tag_yy, tag_mm = int(parts[0]), int(parts[1])
            if cur_yy != tag_yy or cur_mm != tag_mm:
                base = f"{cur_yy}.{cur_mm}.1"
        except ValueError:
            pass
    return f"{base}.dev{dev}"


def get_core_version(core_root: Path, default: str = "—") -> str:
    try:
        from importlib.metadata import version
        return _clean_version(version("astrapi-core"))
    except Exception:
        return str(_read_yaml(core_root / "core.yaml").get("version", default))
