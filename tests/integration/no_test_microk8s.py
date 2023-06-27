#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import logging

import config
import pytest
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("cp_units, worker_units", config.MK8S_CLUSTER_SIZES)
@pytest.mark.parametrize("series", config.MK8S_SERIES)
async def test_microk8s_cluster(e: OpsTest, series: str, cp_units: int, worker_units: int):
    """Deploy a cluster and wait for units to come up"""

    charm_config = {}
    application_name = f"microk8s-{series or 'default'}-{cp_units}c{worker_units}w"

    apps = []
    apps.append(
        await e.model.deploy(
            config.MK8S_CHARM,
            application_name=application_name,
            num_units=cp_units,
            config=charm_config,
            channel=config.MK8S_CHARM_CHANNEL,
            series=series,
            constraints=config.MK8S_CONSTRAINTS,
        )
    )

    if worker_units > 0:
        apps.append(
            await e.model.deploy(
                config.MK8S_CHARM,
                application_name=f"{application_name}-worker",
                num_units=worker_units,
                config={"role": "worker", **charm_config},
                channel=config.MK8S_CHARM_CHANNEL,
                series=series,
                constraints=config.MK8S_CONSTRAINTS,
            )
        )

        await e.model.add_relation(
            f"{application_name}:workers", f"{application_name}-worker:control-plane"
        )

    await e.model.wait_for_idle([a.name for a in apps], timeout=60 * 60)
    for a in apps:
        await e.model.remove_application(a.name, block_until_done=True)
