#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#
import logging

import config
import pytest
from conftest import available_cloud_types, run_unit
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_ceph_csi(e: OpsTest, charm_config: dict):
    """Integration test for MicroK8s with Ceph CSI operator"""

    if await available_cloud_types(e) == {"lxd"}:
        pytest.skip("Ceph CSI test not supported on LXD cloud, skipping")

    LOG.info("Deploy MicroK8s")
    if "microk8s" not in e.model.applications:
        await e.model.deploy(
            config.MK8S_CHARM,
            application_name="microk8s",
            config=charm_config,
            channel=config.MK8S_CHARM_CHANNEL,
            constraints=config.MK8S_CONSTRAINTS,
        )
        await e.model.wait_for_idle(["microk8s"])

    # deploy ceph
    LOG.info("Deploy Ceph")
    if "ceph-mon" not in e.model.applications:
        await e.model.deploy(
            config.MK8S_CEPH_MON_CHARM,
            application_name="ceph-mon",
            channel=config.MK8S_CEPH_MON_CHANNEL,
            config={"monitor-count": 1},
        )
    if "ceph-osd" not in e.model.applications:
        await e.model.deploy(
            config.MK8S_CEPH_OSD_CHARM,
            application_name="ceph-osd",
            channel=config.MK8S_CEPH_OSD_CHANNEL,
            storage={"osd-devices": {"size": 5120, "count": 3}},
            num_units=2,
        )
        await e.model.integrate("ceph-mon", "ceph-osd")
    await e.model.wait_for_idle(["ceph-mon", "ceph-osd"])

    LOG.info("Deploy Ceph CSI operator")
    if "ceph-csi" not in e.model.applications:
        await e.model.deploy(
            config.MK8S_CEPH_CSI_CHARM,
            application_name="ceph-csi",
            channel=config.MK8S_CEPH_CSI_CHANNEL,
            config={
                "namespace": "kube-system",
                "provisioner-replicas": 1,
            },
        )
        await e.model.add_relation("ceph-mon", "ceph-csi")
        await e.model.add_relation("microk8s:kubernetes-info", "ceph-csi:kubernetes-info")

    await e.model.wait_for_idle(["microk8s", "ceph-csi"])

    unit: Unit = e.model.applications["microk8s"].units[0]
    for attempt in range(10):
        _, stdout, _ = await run_unit(unit, "microk8s kubectl get storageclass")
        LOG.info("(attempt %d) Waiting for Ceph StorageClass to appear", attempt)

        if "ceph-ext4" in stdout and "ceph-xfs" in stdout:
            break

    assert "ceph-ext4" in stdout, "Ceph StorageClasses were not created in time"
