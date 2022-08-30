# MicroK8s

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
mkdir -p ~/.kube
juju run-action microk8s/leader kubeconfig
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
