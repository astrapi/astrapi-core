# core/system/cmd.py
import logging
import socket
import subprocess
from functools import lru_cache

_logger = logging.getLogger(__name__)

# Timeouts für Subprocess-Aufrufe.
# Backup-Jobs können stundenlang laufen → kein globaler Timeout.
# Aber: Info-Abfragen (borg info, borg list) und SSH-Verbindungstests
# sollen nicht ewig hängen.
TIMEOUT_INFO    = 60    # borg info, borg list, rsync --dry-run
TIMEOUT_CONNECT = 15    # SSH-Verbindungstest
TIMEOUT_BACKUP  = None  # Backup selbst: kein Timeout (kann Stunden dauern)


@lru_cache(maxsize=1)
def _local_hostnames() -> frozenset:
    names = set()
    hostname = socket.gethostname()
    fqdn = socket.getfqdn()
    names.add(hostname)
    names.add(fqdn)
    names.add(hostname.split('.')[0])   # Kurzname ohne Domain
    names.add(fqdn.split('.')[0])       # Kurzname ohne Domain
    try:
        names.add(socket.gethostbyname(hostname))
    except OSError:
        pass
    return frozenset(names)


def is_local(host: str) -> bool:
    if not host or host == "local":
        return True
    local = _local_hostnames()
    if host in local:
        return True
    # Kurzname des übergebenen Hosts prüfen ("bart.simpsons.lan" → "bart")
    if host.split('.')[0] in local:
        return True
    return False


def build_connection_string(host: str, ssh_user: str = "backupadm") -> str:
    if is_local(host):
        return "local"
    return f"{ssh_user or 'backupadm'}@{host}"


def run_cmd(cmd, connection: str, env=None, stdin: str | None = None,
            timeout=TIMEOUT_BACKUP, ssh_connect_timeout=10):
    if isinstance(cmd, list):
        cmd = " ".join(cmd)
    if connection == "local":
        return run_cmd_local(cmd, env, timeout=timeout, stdin=stdin)
    else:
        return run_cmd_remote(cmd, connection, timeout=timeout,
                               ssh_connect_timeout=ssh_connect_timeout, stdin=stdin)


def _log_output(result) -> None:
    """Loggt stdout und stderr eines abgeschlossenen Prozesses."""
    for line in (result.stdout or "").splitlines():
        if line.strip():
            _logger.info(line)
    for line in (result.stderr or "").splitlines():
        if line.strip():
            _logger.info(line)


def run_cmd_local(cmd, env=None, timeout=TIMEOUT_BACKUP, stdin: str | None = None):
    final_cmd = ["bash", "-c", cmd]
    try:
        result = subprocess.run(
            final_cmd, check=True, env=env, input=stdin,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout,
        )
        _log_output(result)
        return result
    except subprocess.TimeoutExpired:
        _logger.error(f"Timeout ({timeout}s) beim lokalen Befehl: {cmd[:120]}")
        raise


def run_cmd_remote(cmd, connection, timeout=TIMEOUT_BACKUP, ssh_connect_timeout=10,
                    stdin: str | None = None):
    """Führt cmd per SSH auf connection aus.

    SSH leitet die Umgebung des lokalen Prozesses NICHT automatisch an die
    Remote-Shell weiter (nur was per SendEnv/AcceptEnv erlaubt ist, meist nur
    LANG/LC_*). Ein env-Parameter hier wäre deshalb wirkungslos -- es gibt
    bewusst keinen. Geheimnisse gehören nicht als "VAR=wert"-Prefix in cmd
    (landet auf dem Zielhost in ps/proc/<pid>/cmdline, siehe T-052), sondern
    per stdin: Tools wie borg/proxmox-backup-client lesen Passphrase/Passwort
    ueber eine "_FD"-Variable (z.B. BORG_PASSPHRASE_FD=0) von einem
    File-Descriptor. Nur die FD-Nummer steht dann in cmd, kein Geheimnis.
    """
    final_cmd = ["ssh", "-o", "BatchMode=yes",
                 "-o", f"ConnectTimeout={ssh_connect_timeout}",
                 connection, cmd]
    try:
        result = subprocess.run(
            final_cmd, check=True, input=stdin,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout,
        )
        _log_output(result)
        return result
    except subprocess.TimeoutExpired:
        _logger.error(f"Timeout ({timeout}s) beim Remote-Befehl auf {connection}: {cmd[:120]}")
        raise
