# MicroK8s

### **WARNING**: This charm should not be used to deploy production-grade MicroK8s clusters, as it lacks critical features such as LMA integration, backup, restore, upgrades, etc. Use at your own risk. Refer to https://microk8s.io/docs for more details on how to deploy MicroK8s.

## The smallest, fastest Kubernetes

Single-package fully conformant lightweight Kubernetes that works on [42 flavours of Linux](https://snapcraft.io/microk8s). Perfect for:

- Developer workstations
- IoT
- Edge
- CI/CD

## Usage

This charm deploys and manages a MicroK8s cluster. It can handle scaling up and down.

**Minimum Requirements**: 1 vCPU and 1GB RAM.

**Recommended Requirements**: 2 vCPUs and 4GB RAM, 20GB disk.

Make sure to account for extra requirements depending on the workload you are planning to deploy.

```bash
juju deploy microk8s --constraints 'cores=2 mem=4G'
```

Alternatively, to specify the MicroK8s version to install, you can use:

```bash
juju deploy microk8s --constraints 'cores=2 mem=4G' --config channel=1.25
```

Then, retrieve the kubeconfig file with:

```bash
# For Juju 3.1 or newer
mkdir -p ~/.kube
juju run microk8s/leader kubeconfig
juju ssh microk8s/leader cat config | tee ~/.kube/config

# For older Juju versions
mkdir -p ~/.kube
juju run microk8s/leader kubeconfig
juju scp microk8s/leader:config ~/.kube/config
```

In some clouds (e.g. OpenStack), you will need to expose the application before you can access it from the external network:

```bash
juju expose microk8s
```

### Addons

Enable addons with:

```bash
juju config microk8s addons='storage dns ingress'
```

### Scale Out Usage

```bash
juju add-unit -n 2 microk8s
```

### Proxy configuration

In constrained environments, or environments where a proxy should be used for accessing image registries (e.g. DockerHub), you can configure HTTP proxy settings for containerd like so:

```bash
echo '
# This file is managed by Juju. Manual changes may be lost at any time.
# Configure limits for locked memory and maximum number of open files
ulimit -n 65536 || true
ulimit -l 16384 || true
# Configure a proxy for containerd
HTTP_PROXY=http://squid.internal:3128
HTTPS_PROXY=http://squid.internal:3128
NO_PROXY=10.0.0.0/8,127.0.0.1,192.168.0.0/16
' > containerd_env
juju config microk8s containerd_env=@containerd_env
```

## Testing

### Unit tests

```bash
tox
```

### Integration tests

The integration tests require a bootstrapped Juju controller.

```bash
./integration_tests.sh
```

## Build from source

```bash
charmcraft pack
```
