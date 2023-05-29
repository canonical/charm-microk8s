#
# Copyright 2023 Canonical, Ltd.
#
import logging
import os
import shlex
import subprocess

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
