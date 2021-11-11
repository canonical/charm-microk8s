# microk8s

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
juju deploy --constraints 'cores=2 mem=4G' microk8s
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

### LXD

```bash
cp hacks/lxd-profile.yaml .
charmcraft pack
```
