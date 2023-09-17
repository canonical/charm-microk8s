#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import json
import logging

import config
import pytest
from conftest import microk8s_kubernetes_cloud_and_model, run_unit
from juju.application import Application
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_cos(e: OpsTest, charm_config: dict):
    # deploy microk8s
    if "microk8s" not in e.model.applications:
        await e.model.deploy(
            config.MK8S_CHARM,
            application_name="microk8s",
            config={**charm_config, "hostpath_storage": "true"},
            channel=config.MK8S_CHARM_CHANNEL,
            constraints=config.MK8S_CONSTRAINTS,
        )
        await e.model.wait_for_idle(["microk8s"])

    if "grafana-agent" not in e.model.applications:
        await e.model.deploy(
            config.MK8S_GRAFANA_AGENT_CHARM,
            channel=config.MK8S_GRAFANA_AGENT_CHANNEL,
            application_name="grafana-agent",
        )
        await e.model.add_relation("microk8s", "grafana-agent")
        await e.model.wait_for_idle(["microk8s", "grafana-agent"], raise_on_error=False)

    microk8s_unit: Unit = e.model.applications["microk8s"].units[0]
    grafana_agent_app: Application = e.model.applications["grafana-agent"]

    # bootstrap a juju cloud on the deployed microk8s
    async with microk8s_kubernetes_cloud_and_model(e, "microk8s") as (k8s_model, k8s_model_name):
        with e.model_context(k8s_model):
            LOG.info("Deploy MetalLB")
            await e.model.deploy(
                config.MK8S_METALLB_CHARM,
                application_name="metallb",
                config={"iprange": "10.42.42.42-10.42.42.42"},
                channel=config.MK8S_METALLB_CHANNEL,
            )
            await e.model.wait_for_idle(["metallb"])

            LOG.info("Deploy cos-lite")
            await e.model.deploy(
                config.MK8S_COS_BUNDLE,
                channel=config.MK8S_COS_CHANNEL,
                trust=True,
            )
            await e.model.wait_for_idle(["prometheus"], timeout=30 * 60)

            LOG.info("Create offers for cos-lite endpoints")
            await e.model.create_offer("prometheus:receive-remote-write", "prometheus")
            await e.model.create_offer("loki:logging", "loki")
            await e.model.create_offer("grafana:grafana-dashboard", "grafana")

        try:
            LOG.info("Consume cos-lite and relate with grafana-agent")
            await e.model.consume(f"admin/{k8s_model_name}.prometheus", "prometheus")
            await e.model.consume(f"admin/{k8s_model_name}.loki", "loki")
            await e.model.consume(f"admin/{k8s_model_name}.grafana", "grafana")
            await e.model.add_relation("grafana-agent", "prometheus")
            await e.model.add_relation("grafana-agent", "loki")
            await e.model.add_relation("grafana-agent", "grafana")

            await e.model.wait_for_idle(["microk8s", "grafana-agent"], timeout=20 * 60)

            hostname = microk8s_unit.machine.hostname
            for query in [
                'up{job="kubelet", node="%s", metrics_path="/metrics"} > 0' % hostname,
                'up{job="kubelet", node="%s", metrics_path="/metrics/cadvisor"} > 0' % hostname,
                'up{job="kubelet", node="%s", metrics_path="/metrics/probes"} > 0' % hostname,
                'up{job="apiserver"} > 0',
                'up{job="kube-controller-manager"} > 0',
                'up{job="kube-scheduler"} > 0',
                'up{job="kube-proxy"} > 0',
                'up{job="kube-state-metrics"} > 0',
            ]:
                while True:
                    try:
                        rc, stdout, stderr = await run_unit(
                            microk8s_unit,
                            f"""
                            curl --silent \
                                http://10.42.42.42/{k8s_model_name}-prometheus-0/api/v1/query \
                                --data-urlencode query='{query}'
                            """,
                        )
                        if rc != 0:
                            raise ValueError("failed to query")

                        response = json.loads(stdout)
                        if response["status"] != "success":
                            raise ValueError("query not successful")
                        if not response["data"]["result"]:
                            raise ValueError("no data yet")

                        LOG.info("Validated query %s", query)
                        break

                    except (ValueError, json.JSONDecodeError, KeyError) as exc:
                        LOG.warning("%s failed: %s\ncurl: %s", query, exc, (rc, stdout, stderr))

            LOG.info("Success! Starting teardown of the environment")

        finally:
            await grafana_agent_app.remove_relation("grafana-dashboards-provider", "grafana")
            await grafana_agent_app.remove_relation("send-remote-write", "prometheus")
            await grafana_agent_app.remove_relation("logging-consumer", "loki")
            await e.model.remove_saas("prometheus")
            await e.model.remove_saas("loki")
            await e.model.remove_saas("grafana")
            await e.model.wait_for_idle(["grafana-agent", "microk8s"])
