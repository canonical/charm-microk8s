# 🚧 Deprecation Notice 🚧
This charm is no longer under active development and there will be no further updates. For similar functionality, consider the currently-in-development [‘k8s’ charm](https://charmhub.io/k8s).

# MicroK8s

## The smallest, fastest Kubernetes

Single-package fully conformant lightweight Kubernetes that works on [42 flavours of Linux](https://snapcraft.io/microk8s). Perfect for:

- Developer workstations
- IoT
- Edge
- CI/CD

## Usage

This charm deploys and manages a MicroK8s cluster. It can handle scaling up and down.

**Minimum Requirements**: 1 vCPU and 2GB RAM.

**Recommended Requirements**: 2 vCPUs and 4GB RAM, 20GB disk.

Make sure to account for extra requirements depending on the workload you are planning to deploy.

```bash
juju deploy microk8s --constraints 'cores=2 mem=4G'
```

Alternatively, to specify the MicroK8s version to install, you can use:

```bash
juju deploy microk8s --constraints 'cores=2 mem=4G' --config channel=1.25
```
