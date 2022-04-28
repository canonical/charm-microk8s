import logging
import os
import re

import pytest
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("snap_channel", os.getenv("MK8S_SNAP_CHANNELS", "").split() or [""])
@pytest.mark.parametrize("series", os.getenv("MK8S_SERIES", "").split() or ["focal", "jammy"])
async def test_deploy_cluster(ops_test: OpsTest, snap_channel: str, series: str):
    units = int(os.getenv("MK8S_CLUSTER_SIZE", 3))
    charm = os.getenv("MK8S_CHARM", "microk8s")
    constraints = os.getenv("MK8S_CONSTRAINTS", "mem=4G root-disk=20G cores=2")
    charm_channel = os.getenv("MK8S_CHARM_CHANNEL")
    proxy = os.getenv("MK8S_PROXY")
    no_proxy = os.getenv("MK8S_NO_PROXY")

    if charm == "build":
        LOG.info("Build charm")
        charm = await ops_test.build_charm(".")

    if proxy is not None:
        LOG.info("Configure model to use proxy %s", proxy)
        await ops_test.model.set_config(
            {
                "http-proxy": proxy,
                "https-proxy": proxy,
                "ftp-proxy": proxy,
            }
        )
    if no_proxy is not None:
        LOG.info("Configure model no_proxy %s", no_proxy)
        await ops_test.model.set_config({"no-proxy": no_proxy})

    charm_config = {}
    application_name = None
    if snap_channel:
        application_name = re.sub("[^a-z0-9]", "", "microk8s{}".format(snap_channel))
        charm_config["channel"] = snap_channel
    if proxy:
        charm_config["containerd_env"] = "\n".join(
            [
                "ulimit -n 65536 || true",
                "ulimit -l 16834 || true",
                "HTTP_PROXY={}".format(proxy),
                "HTTPS_PROXY={}".format(proxy),
                "NO_PROXY={}".format(no_proxy),
            ]
        )

    LOG.info("Deploy microk8s charm %s on %s with configuration %s", charm, series, charm_config)
    app = await ops_test.model.deploy(
        charm,
        application_name=application_name,
        num_units=units,
        config=charm_config,
        channel=charm_channel,
        constraints=constraints,
        series=series,
        force=True,
    )

    LOG.info("Wait for cluster")
    await ops_test.model.wait_for_idle(apps=[app.name], timeout=60 * 60)

    await ops_test.model.applications[app.name].remove()
