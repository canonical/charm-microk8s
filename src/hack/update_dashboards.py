#
# Copyright 2023 Canonical, Ltd.
#

# Sync Grafana dashboards from https://github.com/prometheus-operator/kube-prometheus
# Dashboard changes:
# - Remove built-in $prometheus datasource (COS adds the datasource automatically)

import json
import os
import shutil
from urllib.request import urlopen

import yaml

SOURCE = "https://raw.githubusercontent.com/prometheus-operator/kube-prometheus/main/manifests/grafana-dashboardDefinitions.yaml"  # noqa

DASHBOARDS = [
    # "alertmanager-overview.json",
    "apiserver.json",
    "cluster-total.json",
    "controller-manager.json",
    # "grafana-overview.json",
    "k8s-resources-cluster.json",
    "k8s-resources-multicluster.json",
    "k8s-resources-namespace.json",
    "k8s-resources-node.json",
    "k8s-resources-pod.json",
    "k8s-resources-workload.json",
    "k8s-resources-workloads-namespace.json",
    "kubelet.json",
    "namespace-by-pod.json",
    "namespace-by-workload.json",
    # "node-cluster-rsrc-use.json",
    # "node-rsrc-use.json",
    # "nodes-darwin.json",
    # "nodes.json",
    "persistentvolumesusage.json",
    "pod-total.json",
    # "prometheus-remote-write.json",
    # "prometheus.json",
    "proxy.json",
    "scheduler.json",
    "workload-total.json",
]

DIR = "src/grafana_dashboards"

shutil.rmtree(DIR, ignore_errors=True)
os.mkdir(DIR)

with urlopen(SOURCE) as request:
    data = yaml.safe_load(request.read())

    for cm in data["items"]:
        for key, value in cm["data"].items():
            if key not in DASHBOARDS:
                continue

            json_value = json.loads(value)

            # drop builtin prometheus datasource
            for idx, val in enumerate(json_value["templating"]["list"]):
                if val["name"] == "datasource" and val["type"] == "datasource":
                    del json_value["templating"]["list"][idx]
                    break

            value = json.dumps(json_value, indent=4)

            # COS requires $prometheusds for the datasource name
            value = value.replace("$datasource", "$prometheusds")

            with open(f"{DIR}/{key}", "w") as fout:
                fout.write(value)
