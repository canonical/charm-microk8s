## MicroK8s Charm

### Overview

```bash
# deploy 3 control plane nodes, 3 worker nodes
juju deploy microk8s -n 3
juju deploy microk8s microk8s-worker -n 3 --config role=worker

# connect worker nodes to the control plane
juju relate microk8s:microk8s-provides microk8s-worker:microk8s
```

The control plane nodes will automatically form a 3-node cluster. The worker nodes will stay in a waiting state until they are related to the control plane.

### Relations

![relations](./fsm/relations.png)

| Charm Role    | Relation          | Interface     | Description                                | Application Data                                      | Unit Data        |
| ------------- | ----------------- | ------------- | ------------------------------------------ | ----------------------------------------------------- | ---------------- |
| control-plane | peer              | microk8s-peer | Offer join url to peer control plane nodes | write `join_url` (leader), read `join_url` (follower) | write `hostname` |
| worker        | peer              | microk8s-peer | Unused                                     |                                                       |                  |
| control-plane | microk8s-provides | microk8s-info | Offer join url to worker nodes             | write `join_url`                                      | read `hostname`  |
| worker        | microk8s          | microk8s-info | Retrieve join url from control plane       | read `join_url`                                       | write `hostname` |

### Control Plane

When deploying the charm with `role=""` or `role="control-plane"`, the charm will bootstrap a control plane and automatically cluster all peers. The state machine implemented by the charm is shown in the figure below:

![control plane](./fsm/control-plane.png)

- The leader unit generates and shares a `join_url` for joining other (control plane or worker) nodes to the cluster. The join_url is shared using the `peer` (follower units) and `microk8s-provides` (worker units) relations.
- All control plane units announce their hostname through the `peer` relation.
- The leader unit takes care of removing nodes (using `microk8s remove-node --force`) after they have left the cluster.

### Worker

When deploying the charm with `role="worker"`, the charm will deploy worker-only nodes. The nodes will wait for a `microk8s` relation to an existing microk8s control plane application.

![worker](./fsm/worker.png)
