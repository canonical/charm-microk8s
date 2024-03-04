import json
import logging
import os
import shlex
import subprocess
import time
from pathlib import Path
from time import sleep


logger = logging.getLogger(__name__)


def get_departing_unit_name():
    return os.environ.get("JUJU_DEPARTING_UNIT")


def join_url_from_add_node_output(output):
    """Extract the first join URL from the output of `microk8s add-node`."""
    lines = output.split("\n")
    lines = [line.strip() for line in lines]
    lines = [line for line in lines if line.startswith("microk8s join ")]
    return lines[0].split()[2]


class KubectlFailedError(Exception):
    pass


class MicroK8sNode:
    def __init__(self, result):
        self._result = result

    def exists(self):
        if self._result.returncode == 0:
            return True
        if "NotFound" in self._result.stderr:
            return False
        raise KubectlFailedError("kubectl failed with no error output, rc={}".format(self._result.returncode))

    def ready(self):
        if not self.exists():
            return False
        parsed = json.loads(self._result.stdout)
        conditions = parsed.get("status", {}).get("conditions", [])
        ready_conditions = [
            condition
            for condition in conditions
            if condition.get("type") == "Ready" and condition.get("reason") == "KubeletReady"
        ]
        if len(ready_conditions) != 1:
            return
        return ready_conditions[0].get("status") == "True"


def get_microk8s_node(node_name):
    return MicroK8sNode(
        subprocess.run(
            ["/snap/bin/microk8s", "kubectl", "get", "node", node_name, "-o", "json"],
            capture_output=True,
            encoding="utf-8",
        )
    )


def get_microk8s_nodes_json():
    return subprocess.check_output(
        ["/snap/bin/microk8s", "kubectl", "get", "nodes", "-o", "json"],
        encoding="utf-8",
    )


def join_url_key(unit):
    return unit.name + ".join_url"


def close_port(port):
    subprocess.check_call(["close-port", port])


def open_port(port):
    subprocess.check_call(["open-port", port])


def microk8s_ready():
    """Check if microk8s is ready.

    Since `microk8s status` usually exits 0, we do this by parsing its output.
    """
    result = subprocess.run(
        ["/snap/bin/microk8s", "status"],
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode > 0:
        return False
    return result.stdout.startswith("microk8s is running")


def retry_until_zero_rc(cmd, max_tries, timeout_seconds):
    """Run cmd, and retry while it has a non-zero return code."""
    for i in range(max_tries):
        try:
            subprocess.check_call(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            break
        except subprocess.CalledProcessError as e:
            if i == max_tries - 1:
                raise e

            logger.exception(
                "Command %s failed with return code %d\nStdout: %s\nStderr: %s\n",
                cmd,
                e.returncode,
                e.stdout,
                e.stderr,
            )
            sleep(timeout_seconds)


def get_kubernetes_version_from_channel(channel: str) -> list:
    """Retrieve the Kubernetes version implied by a snap channel."""
    track = channel.split("/")[0]
    return list(map(int, track.split(".")))


def check_kubernetes_version_is_older(current: str, new: str):
    """Check if the Kubernetes version implied by channel new is older than the current."""
    try:
        current_version = get_kubernetes_version_from_channel(current)
        new_version = get_kubernetes_version_from_channel(new)
        return current_version > new_version
    except (TypeError, ValueError):
        return False


def run(*args, **kwargs) -> subprocess.CompletedProcess:
    """log and run command"""
    kwargs.setdefault("check", True)

    logger.debug("Execute: %s (args=%s, kwargs=%s)", shlex.join(args[0]), args, kwargs)
    return subprocess.run(*args, **kwargs)


def ensure_file(file: Path, data: str, permissions: int = None, uid: int = None, gid: int = None) -> bool:
    """ensure file with specific contents, owner:group and permissions exists on disk.
    returns `True` if file contents have changed"""

    # ensure directory exists
    file.parent.mkdir(parents=True, exist_ok=True)

    changed = False
    if not file.exists() or file.read_text() != data:
        file.write_text(data)
        changed = True

    if permissions is not None:
        os.chmod(file, permissions)

    if uid is not None and gid is not None:
        os.chown(file, uid, gid)

    return changed


def ensure_block(data: str, block: str, block_marker: str) -> str:
    """return a copy of data and ensure that it contains `block`, surrounded by the specified
    `block_marker`. `block_marker` can contain `{mark}`, which is replaced with begin and end
    """

    if block_marker:
        marker_begin = "\n" + block_marker.replace("{mark}", "begin") + "\n"
        marker_end = "\n" + block_marker.replace("{mark}", "end") + "\n"
    else:
        marker_begin, marker_end = "\n", "\n"

    begin_index = data.rfind(marker_begin)
    end_index = data.find(marker_end, begin_index + 1)

    if begin_index == -1 or end_index == -1:
        return f"{data}{marker_begin}{block}{marker_end}"

    return f"{data[:begin_index]}{marker_begin}{block}{data[end_index:]}"


def _ensure_func(f: callable, args: list, kwargs: dict, retry_on, max_retries: int = 10, backoff: int = 2):
    """run a function until it does not raise one of the exceptions from retry_on"""
    for idx in range(max_retries - 1):
        try:
            return f(*args, **kwargs)
        except retry_on:
            logger.exception("action not successful (try %d of %d)", idx + 1, max_retries)
            time.sleep(backoff)

    # last time run unprotected and raise any exception
    return f(*args, **kwargs)


def ensure_call(*args, **kwargs) -> subprocess.CompletedProcess:
    """repeatedly run a command until it succeeds. any args are passed to subprocess.check_call"""
    return _ensure_func(run, args, kwargs, subprocess.CalledProcessError)
