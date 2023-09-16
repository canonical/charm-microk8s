#
# Copyright 2023 Canonical, Ltd.
#
import logging
from contextlib import asynccontextmanager
from typing import Tuple

import config
import pytest
import pytest_asyncio
from juju.action import Action
from juju.application import Application
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)


@pytest_asyncio.fixture(scope="module")
async def e(ops_test: OpsTest):
    """fixture to setup environment and configuration settings on the testing model."""

    if config.MK8S_CHARM == "build":
        config.MK8S_CHARM = await ops_test.build_charm(".")

    model_config = {"logging-config": "<root>=INFO;unit=DEBUG"}
    if config.MK8S_PROXY is not None:
        model_config["http-proxy"] = config.MK8S_PROXY
        model_config["https-proxy"] = config.MK8S_PROXY
        model_config["ftp-proxy"] = config.MK8S_PROXY
    if config.MK8S_NO_PROXY is not None:
        model_config["no-proxy"] = config.MK8S_NO_PROXY

    await ops_test.model.set_config(model_config)

    yield ops_test


@pytest.fixture(scope="module")
def charm_config():
    """fixture with common microk8s charm configuration settings."""
    charm_config = {}
    if config.MK8S_PROXY is not None:
        charm_config["containerd_http_proxy"] = config.MK8S_PROXY
        charm_config["containerd_https_proxy"] = config.MK8S_PROXY
    if config.MK8S_NO_PROXY is not None:
        charm_config["containerd_no_proxy"] = config.MK8S_NO_PROXY

    yield charm_config


async def run_unit(unit: Unit, command: str) -> Tuple[int, str, str]:
    """
    execute a command on the specified unit. Returns the exit code, stdout and stderr. Handles
    differences between Juju 2.9 and 3.1
    """
    action: Action = await unit.run(command)

    output = await unit.model.get_action_output(action.entity_id)

    if "return-code" in output:
        # Juju 3.1
        return output["return-code"], output.get("stdout") or "", output.get("stderr") or ""
    elif "Code" in output:
        # Juju 2.9
        return int(output["Code"]), output.get("Stdout") or "", output.get("Stderr") or ""

    raise ValueError(f"unknown action output {output}")


@asynccontextmanager
async def microk8s_kubernetes_cloud_and_model(ops_test: OpsTest, microk8s_application: str):
    """
    Usage:

    ```
    async with microk8s_kubernetes_cloud_and_model(ops_test, "microk8s") as k8s_model:
        with ops_test.model_context(k8s_model):
            ops_test.deploy( <kubernetes things> )

        ops_test.deploy( <main model things> )
    ```
    """
    app: Application = ops_test.model.applications[microk8s_application]

    await app.expose()
    await app.set_config({"hostpath_storage": "true"})

    await ops_test.model.wait_for_idle([microk8s_application])

    rc, kubeconfig, _ = await run_unit(app.units[0], "microk8s config -l")
    if rc != 0:
        raise Exception(f"failed to retrieve microk8s config {rc, kubeconfig}")

    # In some clouds the IP in kubeconfig returned by microk8s config is not the public IP
    # where the API server is found.
    kubeconfig = kubeconfig.replace("127.0.0.1", app.units[0].public_address)
    cloud_name = f"k8s-{ops_test._generate_model_name()}"
    model_name = f"k8s-{ops_test._generate_model_name()}"

    try:
        LOG.info("Add cloud %s on controller %s", cloud_name, ops_test.controller_name)
        await ops_test.juju(
            "add-k8s",
            cloud_name,
            "--client",
            "--controller",
            ops_test.controller_name,
            stdin=kubeconfig.encode(),
        )

        await ops_test.track_model(
            "k8s-model",
            model_name=model_name,
            cloud_name=cloud_name,
            credential_name=cloud_name,
        )

        yield ("k8s-model", model_name)
    finally:
        if "k8s-model" in ops_test.models:
            await ops_test.forget_model("k8s-model")
            LOG.info("Destroy model %s", model_name)
            res = await ops_test.juju(
                "destroy-model", model_name, "--force", "--destroy-storage", "--yes", "--no-prompt"
            )
            LOG.info("%s", res)

        LOG.info("Delete cloud 'k8s-cloud' on controller '%s'", ops_test.controller_name)
        res = await ops_test.juju(
            "remove-k8s", cloud_name, "--client", "--controller", ops_test.controller_name
        )
        LOG.info("%s", res)
