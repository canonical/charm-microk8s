## Vault CA

### (UX)

```bash
juju deploy microk8s
juju deploy vault

# ... configure vault ...

juju relate microk8s:tls-certificates vault
```

control plane:
- microk8s/0 (*)
- microk8s/1

workers:
microk8s-worker/0
microk8s-worker/1
microk8s-worker/2

relations:
- microk8s:tls-certificates <-> vault:tls
- microk8s:peer <-> microk8s:peer
- microk8s:workers <-> microk8s-worker:control-plane

### Overview

1. When the tls-certificates relation is available, the `leader` unit will request for an intermediate CA certificate from Vault.
2. After the intermediate CA is available, the `leader` unit shares the CA certificate and key with the rest of the cluster nodes (control plane and workers), by writing it to
   1. `peer_relation_data[app].ca_crt` and `peer_relation_data[app].ca_key` for control plane units
   2. `worker_relation_data[app].ca_crt` for worker units
3. Control plane units check if a `ca_crt` is set on the peer relation. If different from their own CA, they use `microk8s refresh-certs`. On success, they set `configured_ca_crt`
4. Worker units check if a `ca_crt` is set on the worker relation. If different from their own CA, they repeat the `microk8s join` command to get the new CA. On success, they set `configured_ca_crt`
5. The leader unit waits for all control plane and worker units to set the `configured_ca_crt`. Once set, it performs final actions:
   1. Restart calico so that it picks up the new CA (`microk8s kubectl rollout restart ds/calico-node -n kube-system`)
   2. Delete `kube-root-ca.crt` configmaps from all namespaces. kube-apiserver will recreate them with the new CA. This is important for pods that talk to the apiserver and need the CA
   3. Kos said kill everything with fire. I don't agree
6. Documentation.
7. Integration tests for Vault. Make sure everything works and reconciles properly.

### Vault support

- https://github.com/juju-solutions/interface-tls-certificates/pull/31
- (currently WIP) https://review.opendev.org/c/openstack/charm-vault/+/897871
