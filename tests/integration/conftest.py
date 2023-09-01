#
# Copyright 2023 Canonical, Ltd.
#
import logging
from contextlib import asynccontextmanager
from typing import Tuple

import config
import pytest_asyncio
import yaml
from juju.action import Action
from juju.application import Application
from juju.unit import Unit
from juju.utils import block_until_with_coroutine
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

    rc, kubeconfig, _ = await run_unit(app.units[0], "microk8s config")
    if rc != 0:
        raise Exception(f"failed to retrieve microk8s config {rc, kubeconfig}")

    model_name = f"k8s-{ops_test._generate_model_name()}"

    try:
        LOG.info("Add cloud %s on controller %s", JUJU_CLOUD_NAME, ops_test.controller_name)
        await ops_test.juju(
            "add-k8s",
            JUJU_CLOUD_NAME,
            "--client",
            "--controller",
            ops_test.controller_name,
            stdin=kubeconfig.encode(),
        )

        await ops_test.track_model(
            "k8s-model",
            model_name=model_name,
            cloud_name=JUJU_CLOUD_NAME,
            credential_name=JUJU_CLOUD_NAME,
        )

        yield ("k8s-model", model_name)

    finally:
        LOG.info("Destroy model %s", model_name)
        timeout = 5 * 60
        await ops_test.forget_model("k8s-model", destroy_storage=True, timeout=timeout)

        async def model_removed():
            rc, stdout, _ = await ops_test.juju("models", "--format", "yaml")
            if rc != 0:
                return False
            model_list = yaml.safe_load(stdout)["models"]
            return len([m for m in model_list if m["name"] == f"admin/{model_name}"]) == 0

        await block_until_with_coroutine(model_removed, timeout=timeout)
        LOG.info("Delete cloud 'k8s-cloud' on controller '%s'", ops_test.controller_name)
        res = await ops_test.juju(
            "remove-k8s", JUJU_CLOUD_NAME, "--client", "--controller", ops_test.controller_name
        )
        LOG.info("%s", res)
