#
# Copyright 2023 Canonical, Ltd.
#
import logging
from contextlib import asynccontextmanager

import config
import pytest_asyncio
from juju.action import Action
from juju.application import Application
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)

JUJU_CLOUD_NAME = "microk8s-cloud"


@pytest_asyncio.fixture(scope="module")
async def e(ops_test: OpsTest):
    """fixture to setup environment and configuration settings on the testing model."""

    if config.MK8S_CHARM == "build":
        config.MK8S_CHARM = await ops_test.build_charm(".")

    model_config = {"logging-config": "<root>=INFO;unit=DEBUG"}
    if config.MK8S_PROXY is not None:
        model_config.update(
            {
                "http-proxy": config.MK8S_PROXY,
                "https-proxy": config.MK8S_PROXY,
                "ftp-proxy": config.MK8S_PROXY,
            }
        )
    if config.MK8S_NO_PROXY is not None:
        model_config.update({"no-proxy": config.MK8S_NO_PROXY})

    await ops_test.model.set_config(model_config)

    yield ops_test


@asynccontextmanager
async def microk8s_kubernetes_cloud_and_model(ops_test: OpsTest, microk8s_application: str):
    """
    Usage:

    ```
    async with microk8s_kubernetes_cloud_and_model(ops_test, "microk8s") as k8s_model:
        with ops_test.model_context(k8s_model):
            ops_test.deploy( <kubernetes things> )
    ```
    """
    app: Application = ops_test.model.applications[microk8s_application]

    await app.expose()
    await app.set_config({"hostpath_storage": "true"})

    await ops_test.model.wait_for_idle([microk8s_application])

    unit: Unit = app.units[0]
    action: Action = await unit.run("microk8s config")

    result = await ops_test.model.get_action_output(action.entity_id)
    if result["Code"] != "0":
        raise Exception(f"failed to retrieve microk8s config, result was {result}")

    kubeconfig = result["Stdout"]
    model_name = f"k8s-{ops_test._generate_model_name()}"

    try:
        LOG.info("Bootstrap cloud 'k8s-cloud' on controller '%s'", ops_test.controller_name)
        await ops_test.juju(
            "add-k8s",
            JUJU_CLOUD_NAME,
            "--client",
            "--controller",
            ops_test.controller_name,
            stdin=kubeconfig.encode(),
        )

        LOG.info("Create model 'k8s-model' on cloud 'k8s-cloud'")
        await ops_test.track_model(
            "k8s-model",
            model_name=model_name,
            cloud_name=JUJU_CLOUD_NAME,
            credential_name=JUJU_CLOUD_NAME,
            keep=True,
        )
        LOG.info("Created model 'k8s-model' on cloud 'k8s-cloud'")

        yield "k8s-model"

    finally:
        LOG.info("Destroy model 'k8s-model'")
        res = await ops_test.juju(
            "destroy-model", model_name, "--force", "--destroy-storage", "--yes"
        )
        LOG.info("%s", res)
        LOG.info("Delete cloud 'k8s-cloud' on controller '%s'", ops_test.controller_name)
        res = await ops_test.juju(
            "remove-k8s", JUJU_CLOUD_NAME, "--client", "--controller", ops_test.controller_name
        )
        LOG.info("%s", res)
