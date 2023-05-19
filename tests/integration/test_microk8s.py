#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import json
import logging
import os
import re
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]

MK8S_CHARM = os.getenv("MK8S_CHARM", "microk8s")
MK8S_CHARM_CHANNEL = os.getenv("MK8S_CHARM_CHANNEL", "edge")
MK8S_SNAP_CHANNELS = os.getenv("MK8S_SNAP_CHANNELS", "1.25 1.26 1.27").split(" ")
MK8S_CLUSTER_SIZES = json.loads(os.getenv("MK8S_CLUSTER_SIZES", "[[1, 0], [3, 2]]"))
MK8S_CONSTRAINTS = os.getenv("MK8S_CONSTRAINTS", "mem=4G root-disk=20G")
MK8S_SERIES = os.getenv("MK8S_SERIES", "jammy focal").split(" ")
MK8S_PROXY = os.getenv("MK8S_PROXY")
MK8S_NO_PROXY = os.getenv("MK8S_NO_PROXY")


@pytest_asyncio.fixture(scope="module")
async def e(ops_test: OpsTest):
    """fixture to setup environment and deploy machines. this is done to spin up machines
    only once and save time for individual version tests"""

    global MK8S_CHARM
    if MK8S_CHARM == "build":
        MK8S_CHARM = await ops_test.build_charm(".")

    model_config = {"logging-config": "<root>=INFO;unit=DEBUG"}
    if MK8S_PROXY is not None:
        model_config.update(
            {"http-proxy": MK8S_PROXY, "https-proxy": MK8S_PROXY, "ftp-proxy": MK8S_PROXY}
        )
    if MK8S_NO_PROXY is not None:
        model_config.update({"no-proxy": MK8S_NO_PROXY})

    await ops_test.model.set_config(model_config)

    yield ops_test


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("channel", MK8S_SNAP_CHANNELS)
@pytest.mark.parametrize("cp_units, worker_units", MK8S_CLUSTER_SIZES)
@pytest.mark.parametrize("series", MK8S_SERIES)
async def test_deploy(e: OpsTest, series: str, channel: str, cp_units: int, worker_units: int):
    """Deploy a cluster and wait for units to come up"""

    charm_config = {}
    application_name = f"microk8s-{series or 'default'}-{cp_units}c{worker_units}w"
    if channel:
        application_name += "-v" + re.sub("[^a-z0-9]", "", channel)
        charm_config["channel"] = channel

    apps = []
    apps.append(
        await e.model.deploy(
            MK8S_CHARM,
            application_name=application_name,
            num_units=cp_units,
            config=charm_config,
            channel=MK8S_CHARM_CHANNEL,
            series=series,
            constraints=MK8S_CONSTRAINTS,
        )
    )

    if worker_units > 0:
        apps.append(
            await e.model.deploy(
                MK8S_CHARM,
                application_name=f"{application_name}-worker",
                num_units=worker_units,
                config={"role": "worker", **charm_config},
                channel=MK8S_CHARM_CHANNEL,
                series=series,
                constraints=MK8S_CONSTRAINTS,
            )
        )

        await e.model.add_relation(
            f"{application_name}:microk8s-provides", f"{application_name}-worker:microk8s"
        )

    await e.model.wait_for_idle([a.name for a in apps], timeout=60 * 60)
    for a in apps:
        await e.model.remove_application(a.name, block_until_done=True)
