#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import logging

import config
import pytest
from conftest import microk8s_kubernetes_cloud_and_model
from juju.action import Action
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_metallb(e: OpsTest):
    # deploy microk8s
    if "microk8s" not in e.model.applications:
        await e.model.deploy(
            config.MK8S_CHARM,
            application_name="microk8s",
            config={"hostpath_storage": "true"},
            channel=config.MK8S_CHARM_CHANNEL,
            constraints=config.MK8S_CONSTRAINTS,
        )
        await e.model.wait_for_idle(["microk8s"])

    # bootstrap a juju cloud on the deployed microk8s
    async with microk8s_kubernetes_cloud_and_model(e, "microk8s") as k8s_model:
        with e.model_context(k8s_model):
            LOG.info("Deploy MetalLB")
            await e.model.deploy(
                config.MK8S_METALLB_SPEAKER_CHARM,
                application_name="metallb-speaker",
            )
            await e.model.deploy(
                config.MK8S_METALLB_CONTROLLER_CHARM,
                application_name="metallb-controller",
                config={"iprange": "42.42.42.42-42.42.42.42"},
            )
            await e.model.wait_for_idle(["metallb-speaker", "metallb-controller"])

        with e.model_context("main"):
            LOG.info("Deploy a test LoadBalancer service")
            u: Unit = e.model.applications["microk8s"].units[0]
            await u.run("microk8s kubectl delete service nginx")
            await u.run("microk8s kubectl create deploy nginx --replicas 3 --image nginx")
            await u.run("microk8s kubectl expose deploy nginx --port 80 --type LoadBalancer")

            result = {}
            while "42.42.42.42" not in (result.get("Stdout") or ""):
                action: Action = await u.run("microk8s kubectl get svc nginx --no-headers")
                result = await e.model.get_action_output(action.entity_id)

                # NOTE(neoaggelos/2023-06-21):
                # result == {"Code": "0", "Stdout": "output from command"}
                LOG.info("Attempt to access load balancer service %s", result)

            LOG.info("LoadBalancer successfully got assigned IP")
