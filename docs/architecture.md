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

### State

| Charm Role | State       | Value                                          | Description                                                                                                                 |
| ---------- | ----------- | ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| all        | `role`      | `""`, `"control-plane"` or `"worker"`          | set to `config["role"]` when the charm is deployed, to prevent the role from changing afterwards                            |
| all        | `installed` | `true` or `false`                              | set to `true` after MicroK8s is installed                                                                                   |
| all        | `joined`    | `true` or `false`                              | set to `true` after joining the cluster successfully                                                                        |
| all        | `leaving`   | `true` or `false`                              | set to `true` if leaving the cluster (relation broken)                                                                      |
| all        | `join_url`  | `"$IP_ADDRESS:25000/$TOKEN"`                   | for units other than the bootstrap control plane node, store the URL that is used to join the cluster                       |
| all        | `hostnames` | `{"microk8s/0": "juju-roasted-beef42-0", ...}` | mapping of unit names to hostnames. recorded by all control plane nodes and used to remove departing nodes from the cluster |

### Relations

![relations](./fsm/relations.png)

| Charm Role    | Relation          | Interface     | Description                                                             | Application Data                                                                        | Unit Data        |
| ------------- | ----------------- | ------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ---------------- |
| control-plane | peer              | microk8s-peer | Offer join url to peer control plane nodes and store clustering actions | write `join_url`, `enabled_addons`, `remove_nodes` (leader), read `join_url` (follower) | write `hostname` |
| worker        | peer              | microk8s-peer | Unused                                                                  |                                                                                         |                  |
| control-plane | microk8s-provides | microk8s-info | Offer join url to worker nodes                                          | write `join_url`                                                                        | read `hostname`  |
| worker        | microk8s          | microk8s-info | Retrieve join url from control plane                                    | read `join_url`                                                                         | write `hostname` |

### Clustering

#### Control Plane

When deploying the charm with `role=""` or `role="control-plane"`, the charm will bootstrap a control plane and automatically cluster all peers. The state machine implemented by the charm is shown in the figure below:

![control plane](./fsm/control-plane.png)

- The leader unit generates and shares a `join_url` for joining other (control plane or worker) nodes to the cluster. The join_url is shared using the `peer` (follower units) and `microk8s-provides` (worker units) relations.
- All control plane units announce their hostname through the `peer` relation.
- The leader unit takes care of removing nodes (using `microk8s remove-node --force`) after they have left the cluster.

#### Worker

When deploying the charm with `role="worker"`, the charm will deploy worker-only nodes. The nodes will wait for a `microk8s` relation to an existing microk8s control plane application.

![worker](./fsm/worker.png)

### Source

The source code is in the `src/` folder and the tests are in `tests/`. The code structure is as follows:

```yaml
charm-microk8s:                     # Root directory
- charmcraft.yaml                   # Charm charmcraft.yaml file
- config.yaml                       # Defines charm configuration options
- metadata.yaml                     # Charm metadata.yaml file
- lxd-profile.yaml                  # LXD profile for the charm to work on LXD
- tox.ini                           # CI and development tooling
- docs:
  - architecture.md                 # Document architecture decisions for the charm
  - development.md                  # Getting started with developing the charm and running tests
- src:
  - charm.py                        # Main charm source code and entry point
  - microk8s.py                     # Implement microk8s functionality
  - util.py                         # Implement helpers and utilities
- tests:
  - unit:
    - conftest.py                   # Shared test fixtures
    - test_charm.py                 # Unit tests for src/charm.py
    - test_charm_control_plane.py   # Unit tests for src/charm.py (control plane specific)
    - test_charm_worker.py          # Unit tests for src/charm.py (worker specific)
    - test_microk8s.py              # Unit tests for src/microk8s.py
    - test_util.py                  # Unit tests for src/util.py
  - integration:
    - config.py                     # Integration tests configuration file
    - test_microk8s.py              # Integration tests
```
