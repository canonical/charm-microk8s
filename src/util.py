#
# Copyright 2023 Canonical, Ltd.
#
import logging
import os
import shlex
import subprocess
from pathlib import Path

LOG = logging.getLogger(__name__)


def check_call(*args, **kwargs):
    """log and run command"""
    LOG.debug("Execute: %s (args=%s, kwargs=%s)", shlex.join(args[0]), args, kwargs)
    return subprocess.check_call(*args, **kwargs)


def install_required_packages():
    """install useful apt packages for microk8s"""

    # FIXME(neoaggelos): these are only really required for OpenEBS. Perhaps we can skip them
    packages = ["nfs-common", "open-iscsi"]

    try:
        packages.append(f"linux-modules-extra-{os.uname().release}")
    except OSError:
        LOG.exception("could not retrieve kernel version, will not install extra modules")

    LOG.info("Installing required packages %s", packages)

    for package in packages:
        try:
            LOG.info("Installing package %s", package)
            check_call(["apt-get", "install", "--yes", package])
        except subprocess.CalledProcessError:
            LOG.exception("failed to install package %s, charm may misbehave", package)


def ensure_file(
    file: Path, data: str, permissions: int = None, uid: int = None, gid: int = None
) -> bool:
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
