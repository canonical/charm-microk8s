## Development Environment

### Tooling

```bash
# format and lint code (always do this before pushing)
tox -e format,lint

# run unit tests
tox -e unit
```

### Run integration tests

Integration tests require a registered Juju controller. You can setup a controller locally using LXD:

```bash
# for juju 2.9
sudo snap install juju --channel 2.9/stable --classic
juju bootstrap lxd
tox -e integration-2.9

# for juju 3.1
sudo snap install juju --channel 3.1/stable
juju bootstrap lxd
tox -e integration-3.1
```

### Local development and testing

When making local changes and deploying the charm:

```bash
# build the charm (microk8s_ubuntu-20.04-amd64_ubuntu-22.04-amd64.charm)
sudo charmcraft pack --destructive-mode

# refresh the application 'application' from the local charm file
juju refresh microk8s --path ./microk8s*.charm
```

Note that blocked units will not be refreshed automatically, you will have to do one of the following:

- `juju resolved microk8s/3` -- unblock the unit (might be blocked again if there is a bug)
- `juju remove-unit microk8s/3 --force && juju add-unit microk8s` -- remove the unit and add a new one
- `juju destroy-model default --force && juju add-model default` -- delete the whole model for more fundamental changes

### Useful debugging notes

#### Observe deployment status

A typical scenario will have a control plane (`microk8s`) and a worker (`microk8s-worker`) application installed and related as shown below. The watch command can be used to keep an eye on the cluster state while testing (e.g. adding, removing nodes)

```bash
$ watch -d -c 'juju status --color --relations; juju run --unit microk8s/leader -- "microk8s kubectl get node -A -o wide; cat /var/snap/microk8s/current/var/kubernetes/backend/cluster.yaml"'

Model    Controller  Cloud/Region  Version  SLA          Timestamp
default  ds          devstack/KHY  2.9.38   unsupported  00:35:02+03:00

App              Version  Status  Scale  Charm     Channel  Rev  Exposed  Message
microk8s                  active      2  microk8s             5  no       node is ready
microk8s-worker           active      3  microk8s             0  no       node is ready

Unit                Workload  Agent  Machine  Public address  Ports                     Message
microk8s-worker/0   active    idle   3        172.16.101.197  80/tcp,443/tcp            node is ready
microk8s-worker/1   active    idle   4        172.16.101.114  80/tcp,443/tcp            node is ready
microk8s-worker/2*  active    idle   5        172.16.101.148  80/tcp,443/tcp            node is ready
microk8s/0          active    idle   0        172.16.101.175  80/tcp,443/tcp,16443/tcp  node is ready
microk8s/5*         active    idle   8        172.16.101.10   80/tcp,443/tcp,16443/tcp  node is ready

Machine  State    Address         Inst id                               Series  AZ    Message
0        started  172.16.101.175  a84a53cd-ac0d-41be-b003-f13b8057b630  focal   nova  ACTIVE
3        started  172.16.101.197  5992965a-1a53-4bb6-a870-4c71f9850eca  focal   nova  ACTIVE
4        started  172.16.101.114  c07c1841-7330-49bd-961b-66f824ee08ea  focal   nova  ACTIVE
5        started  172.16.101.148  c62373d9-a712-4eab-837d-83ed83fb8ffe  focal   nova  ACTIVE
8        started  172.16.101.10   51f75da0-e404-41e9-b45b-9e77f8ecec78  focal   nova  ACTIVE

Relation provider           Requirer                  Interface      Type     Message
microk8s-worker:peer        microk8s-worker:peer      microk8s-peer  peer
microk8s:microk8s-provides  microk8s-worker:microk8s  microk8s-info  regular
microk8s:peer               microk8s:peer             microk8s-peer  peer

NAME                    STATUS   ROLES    AGE   VERSION   INTERNAL-IP      EXTERNAL-IP   OS-IMAGE             KERNEL-VERSION      CONTAINER-RUNTIME
juju-77cee6-default-8   Ready    <none>   18m   v1.26.4   172.16.101.10    <none>        Ubuntu 20.04.6 LTS   5.4.0-148-generic   containerd://1.6.15
juju-77cee6-default-3   Ready    <none>   80m   v1.26.4   172.16.101.197   <none>        Ubuntu 20.04.6 LTS   5.4.0-148-generic   containerd://1.6.15
juju-77cee6-default-5   Ready    <none>   82m   v1.26.4   172.16.101.148   <none>        Ubuntu 20.04.6 LTS   5.4.0-148-generic   containerd://1.6.15
juju-77cee6-default-0   Ready    <none>   80m   v1.26.4   172.16.101.175   <none>        Ubuntu 20.04.6 LTS   5.4.0-148-generic   containerd://1.6.15
juju-77cee6-default-4   Ready    <none>   82m   v1.26.4   172.16.101.114   <none>        Ubuntu 20.04.6 LTS   5.4.0-148-generic   containerd://1.6.15
- Address: 172.16.101.175:19001
  ID: 10110992713028004743
  Role: 0
- Address: 172.16.101.10:19001
  ID: 16011178742223754644
  Role: 2
```

#### Logs

```bash
# show DEBUG logs from unit (print all executed commands, all command outputs)
juju model-config logging-config='<root>=WARNING;unit=DEBUG'

# following debug logs
juju debug-log

# follow logs from unit 'microk8s/3'
juju debug-log --include unit-microk8s-3
```

#### Relation data

For more details, see https://juju.is/docs/sdk/integration. The important details

- Inspect relation data with `juju show-unit microk8s/3`
- All units can read-write their own data (`relation.data[self.unit]`)
- All units can read data from the application `relation.data[self.app]` and other units `relation.data[any_unit]`
- Leader unit can read-write data from the application `relation.data[self.app]`

#### Unit state

Unit state is stored in Juju for persistence. While debugging, you can inspect with:

```bash
$ juju run --unit microk8s/3 -- state-get
'#notices#': |
  []
MicroK8sCharm/StoredStateData[_state]: |
  hostnames: {microk8s-worker/0: juju-77cee6-default-3, microk8s-worker/1: juju-77cee6-default-4,
    microk8s-worker/2: juju-77cee6-default-5, microk8s/0: juju-77cee6-default-0, microk8s/4: juju-77cee6-default-7}
  installed: true
  join_url: 172.16.101.66:25000/30f2e36da1219be11b349a29e164aec5
  joined: true
  leaving: false
  remove_nodes: []
  role: control-plane
StoredStateData[_stored]: |
  {event_count: 81}
```

Note that the state is a YAML formatted string, not a YAML object.

#### Other notes

- Failed hooks (non-zero exit status, uncaught exception, etc) are automatically retried if they initially fail. After a few retries, the unit goes into a blocked state.
- Only the leader unit receives `*-relation-departed` messages.
