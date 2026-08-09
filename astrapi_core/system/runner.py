# core/system/runner.py
"""Wiederverwendbare Logging- und Benachrichtigungs-Helfer für geplante Jobs.

Module nutzen diese Funktionen in ihren ``run()``-Implementierungen:

    from astrapi_core.system.runner import run_all, run_logged

    def run():
        return run_all("borg", _get_config(), run_single)

    # Einzelnen Eintrag mit Activity-Log-Kontext ausführen:
    run_logged("proxmox_lxc", str(item_id), name, lambda: _backup_lxc(...))
"""

import logging
import time

log = logging.getLogger(__name__)

_STATUS_ORDER = {"ok": 0, "warning": 1, "error": 2}


def worst_status(a: str, b: str) -> str:
    """Gibt den schwereren der beiden Status-Strings zurück.

    Rangordnung: ok < warning < error.
    """
    return a if _STATUS_ORDER.get(a, 0) >= _STATUS_ORDER.get(b, 0) else b


def run_logged(module: str, item_id: str, description: str, fn) -> str:
    """Führt ``fn`` mit vollständigem Activity-Log- und Tee-Kontext aus.

    Args:
        module:      Modulname, z.B. ``"borg"``.
        item_id:     ID des Eintrags in der Modul-Config.
        description: Anzeigename für den Log-Eintrag.
        fn:          Callable ohne Argumente.

    Returns:
        Status-String: ``"ok"``, ``"warning"`` oder ``"error"``.
    """
    from astrapi_core.system.activity_log import (
        get_log_lines,
        history_finish,
        history_start,
    )
    from astrapi_core.system.logger import (
        clear_active_log_id,
        clear_tee_context,
        set_active_log_id,
        set_tee_context,
    )

    hist_id = history_start(module, item_id, description, "run")
    t0 = time.time()
    set_tee_context(module, item_id)
    set_active_log_id(hist_id)
    status = "ok"
    try:
        fn()
    except Exception as e:
        status = "error"
        log.error("run_logged: %s/%s fehlgeschlagen: %s", module, item_id, e)
    finally:
        duration = int(time.time() - t0)
        if status == "ok":
            levels = {r["level"] for r in get_log_lines(hist_id)}
            if "ERROR" in levels:
                status = "error"
            elif "WARNING" in levels:
                status = "warning"
        history_finish(hist_id, status, duration)
        clear_active_log_id()
        clear_tee_context()

    return status


def run_all(
    module: str,
    config: dict,
    run_single_fn,
    desc_fn=None,
    mark_pending_fn=None,
) -> str:
    """Führt ``run_single_fn`` für alle aktivierten Einträge in ``config`` aus.

    Args:
        module:       Modulname, z.B. ``"borg"``.
        config:       Dict ``{item_id: entry_dict}`` wie von ``load_config()`` geliefert.
        run_single_fn: Callable ``(item_id, entry)`` – die ``run_single``-Funktion des Moduls.
        desc_fn:      Optionales Callable ``(item_id, entry) -> str`` für den Anzeigenamen.
                      Standard: ``entry.get("description", item_id)``.
        mark_pending_fn: Optionales Callable ``(item_id, entry)``, das vor dem eigentlichen
                      Lauf für **alle** aktivierten Einträge aufgerufen wird – markiert die
                      ganze Liste als "für diesen Job-Lauf eingeplant", bevor der erste
                      Eintrag drankommt. Storage ist je Modul verschieden (core-Config-Tabelle
                      vs. eigener Store), deshalb kein fester Mechanismus, sondern ein Callback.

    Returns:
        ``"ok"`` wenn alle Einträge erfolgreich, ``"error"`` wenn mindestens einer fehlgeschlagen.
    """
    enabled = {
        item_id: entry for item_id, entry in config.items() if entry.get("enabled", True)
    }

    if mark_pending_fn is not None:
        for item_id, entry in enabled.items():
            mark_pending_fn(item_id, entry)

    failed: list[tuple[str, str]] = []
    for item_id, entry in enabled.items():
        desc = (
            desc_fn(item_id, entry)
            if desc_fn is not None
            else entry.get("description", str(item_id))
        )
        status = run_logged(
            module,
            str(item_id),
            desc,
            lambda iid=item_id, e=entry: run_single_fn(iid, e),
        )
        if status == "error":
            failed.append((str(item_id), desc))

    return "error" if failed else "ok"


def _notify(module: str, description: str, status: str, duration: int) -> None:
    """Sendet eine Benachrichtigung über das Ergebnis eines Job-Laufs.

    Args:
        module:      Modulname (wird als Notify-Quelle verwendet).
        description: Anzeigename des Eintrags.
        status:      ``"ok"``, ``"warning"`` oder ``"error"``.
        duration:    Laufzeit in Sekunden.
    """
    try:
        from astrapi_core.modules.notify import engine as _ne

        event = {
            "ok": _ne.SUCCESS,
            "warning": _ne.WARNING,
            "error": _ne.ERROR,
        }.get(status, _ne.INFO)
        status_label = {"ok": "Erfolgreich", "warning": "Warnung", "error": "Fehler"}.get(
            status, status
        )
        _ne.send(
            title=f"{description}: {status_label}",
            message=f"Dauer: {duration}s",
            event=event,
            source=module,
            tags=["job"],
        )
    except Exception as e:
        log.debug("_notify: Benachrichtigung fehlgeschlagen: %s", e)
