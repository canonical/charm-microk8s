#
# Copyright 2023 Canonical, Ltd.
#
import logging
import subprocess

LOG = logging.getLogger(__name__)


def get_unit_public_address():
    """return the public unit address, as reported by Juju"""
    try:
        return subprocess.check_output(["unit-get", "public-address"]).decode().strip()
    except subprocess.CalledProcessError:
        LOG.exception("failed to retrieve public unit address")
        return "127.0.0.1"
