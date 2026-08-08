# core/system/reachability.py
import subprocess
from astrapi_core.system.logger import log
from astrapi_core.system.cmd import is_local


def check_ssh(host: str, user: str = "backupadm", timeout: int = 5, ssh_port: int = None) -> bool:
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={timeout}",
        "-o", "StrictHostKeyChecking=no",
    ]
    if ssh_port and int(ssh_port) != 22:
        cmd += ["-p", str(ssh_port)]
    cmd += [f"{user}@{host}", "echo ok"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and "ok" in result.stdout


def require_hosts(hosts: list, user: str = None) -> bool:
    """
    hosts: list of str, list of (host, user) oder list of (host, user, ssh_port) Tupel.
    user: Fallback-User wenn hosts eine str-Liste ist.
    """
    all_ok = True
    for entry in hosts:
        host_port = None
        if isinstance(entry, tuple):
            if len(entry) >= 3:
                host, host_user, host_port = entry[0], entry[1], entry[2]
            else:
                host, host_user = entry
        else:
            host, host_user = entry, user
        if is_local(host):
            continue
        if not check_ssh(host, host_user, ssh_port=host_port):
            log("WARNING", f"Host nicht erreichbar: {host}")
            log("ERROR", f"SSH-Verbindung zu '{host}' fehlgeschlagen – Ausführung abgebrochen")
            all_ok = False
    return all_ok
