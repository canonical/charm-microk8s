# COS Integration

## (User) Getting Started

This section describes how to deploy a single-node MicroK8s cluster with COS, and then relate MicroK8s with COS to get metrics, logs and dashboards for the cluster.

### Deploy MicroK8s

```bash
# Add a machine model and deploy MicroK8s
juju add-model microk8s
juju deploy microk8s --channel edge --config hostpath_storage=true --constraints 'mem=8G'
juju expose microk8s

# Add MicroK8s as Kubernetes cloud to Juju
juju exec --unit microk8s/leader -- microk8s config | juju add-k8s k8s --controller "$(juju controller-config controller-name)"
```

### Deploy cos-lite

```bash
# Add a Kubernetes model and deploy MetalLB for LoadBalancer support
juju add-model metallb-system k8s
juju deploy metallb-controller --config iprange=10.43.5.10-10.43.5.20
juju deploy metallb-speaker

# Add a Kubernetes model and deploy cos-lite
juju add-model observability k8s
juju deploy cos-lite --trust --channel edge

# Expose metrics, logs and dashboards relations
juju offer prometheus:receive-remote-write prometheus
juju offer loki:logging loki
juju offer grafana:grafana-dashboard grafana
```

### Integrate MicroK8s with COS

```bash
# Switch to 'microk8s' model and configure cross-model relations
juju switch microk8s
juju consume admin/observability.prometheus prometheus
juju consume admin/observability.loki loki
juju consume admin/observability.grafana grafana

# Deploy grafana-agent and integrate grafana-agent with COS
juju deploy grafana-agent --channel edge
juju integrate grafana-agent prometheus
juju integrate grafana-agent loki
juju integrate grafana-agent grafana

# Integrate MicroK8s with grafana-agent
juju integrate microk8s grafana-agent
```

### Access Grafana

Retrieve the admin password for Grafana using:

```bash
juju run --wait -m observability grafana/0 get-admin-password
```

Then, if the LoadBalancer IP is not reachable from your host, create a local port forward:

```bash
juju ssh -m microk8s microk8s/leader -L 8000:10.43.5.10:80
```

Then, point your browser to http://localhost:8000/observability-grafana/ to access Grafana. For debugging purposes, you can also access Prometheus at http://localhost:8000/observability-prometheus-0/

## (Dev) Getting Started

The `microk8s` charm is related with `grafana-agent` through the `cos-agent` relation. The `grafana-agent` is deployed as a subordinate unit on the machines, and is then connected with Prometheus (metrics, alerts), Loki (logs) and Grafana (dashboards) from the COS deployment.

The `microk8s` charm uses the [`COSAgentProvider` library](../lib/charms/grafana_agent/v0/cos_agent.py) to supply the following information to `grafana-agent`:

- **Metrics endpoints**: These are generated in [src/metrics.py](../src/metrics.py). See [Required scrape endpoints](#required-scrape-endpoints) below for the list of scrape configs that are needed.
- **Alert rules**: These are retrieved automatically from the upstream [prometheus-operator/kube-prometheus](https://github.com/prometheus-operator/kube-prometheus) project, using the [src/hack/update_alert_rules.py](../src/hack/update_alert_rules.py) script. The script applies some minor modifications to the alert rules, all of which should be documented in the script itself.
- **Dashboards**: These are retrieved automatically from the upstream [prometheus-operator/kube-prometheus](https://github.com/prometheus-operator/kube-prometheus) project, using the [src/hack/update_dashboards.py](../src/hack/update_dashboards.py) script. The script applies some minor modifications to the dashboards, all of which should be documented in the script itself.

The charm also automatically deploys [`kube-state-metrics`](https://github.com/kubernetes/kube-state-metrics) to the cluster. The manifests for `kube-state-metrics` can be found in [src/deploy/kube-state-metrics.yaml](../src/deploy/kube-state-metrics.yaml) and can be automatically updated using the [src/hack/update_kube_state_metrics.py](../src/hack/update_kube_state_metrics.py) script.

### Implementation Notes and reference

#### Update manifests from upstream projects

To update upstream manifests, use the scripts in `src/hack`.

1. (Optional) Update component versions
   - Check https://github.com/prometheus-operator/kube-prometheus and find a release that is compatible with the MicroK8s version we deploy, then update `VERSION` in `src/hack/update_alert_rules.py` and `src/hack/update_dashboards.py`.
   - Check https://github.com/kubernetes/kube-state-metrics and find a release that is compatible with the MicroK8s version we deploy, then update `VERSION` in `src/hack/update_kube_state_metrics.py`
2. Update vendored manifests from upstream sources

```bash
python src/hack/update_alert_rules.py
python src/hack/update_dashboards.py
python src/hack/update_kube_state_metrics.py

# re-format all files
tox -e format
```

#### Authentication

All Kubernetes metrics endpoints require authentication. Upstream uses a serviceaccount with bearer tokens, but these expire frequently (about 1 hour), so it is not feasible to use them for authentication.

For that matter, we create a ServiceAccount `microk8s-observability` with the appropriate roles and cluster roles, and generate a x509 certificate and private key to authenticate.

#### Required Scrape Endpoints

Since the Kubernetes components are running under the same process, the metrics endpoints return metrics of all components. For that matter, we are using the metrics endpoint of `kube-apiserver` (https://localhost:16443) for all control plane components and `kubelet` (https://localhost:10250) for all worker-node components.

The list of scrape configs below is supposed to match the scrape configs defined by the `kube-prom-stack` project, so that all alert rules and dashboards work out of the box.

| Component               | Metrics endpoints                                                                                            | Node types    | Required labels                                                   |
| ----------------------- | ------------------------------------------------------------------------------------------------------------ | ------------- | ----------------------------------------------------------------- |
| apiserver               | https://localhost:16443/metrics                                                                              | control plane | job="apiserver"                                                   |
| kube-controller-manager | https://localhost:16443/metrics                                                                              | control plane | job="kube-controller-manager"                                     |
| kube-scheduler          | https://localhost:16443/metrics                                                                              | control plane | job="kube-scheduler"                                              |
| kube-proxy              | https://localhost:10250/metrics                                                                              | all           | job="kube-proxy"                                                  |
| kubelet                 | https://localhost:10250/metrics                                                                              | all           | job="kubelet", metrics_path="/metrics", node="$nodename"          |
| kubelet (cadvisor)      | https://localhost:10250/metrics/cadvisor                                                                     | all           | job="kubelet", metrics_path="/metrics/cadvisor", node="$nodename" |
| kubelet (probes)        | https://localhost:10250/metrics/probes                                                                       | all           | job="kubelet", metrics_path="/metrics/probes", node="$nodename"   |
| kube-state-metrics      | https://localhost:16443/api/v1/namespaces/kube-system/services/kube-state-metrics:http-metrics/proxy/metrics | control plane | job="kube-state-metrics"                                          |
