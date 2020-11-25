from ops.framework import Object

from utils import open_port, close_port


class PortManager(Object):
    """Manage ports on all units in the application from a single unit.

    For example, when microk8s enables the ingress addon, it is
    enabled for all nodes in the cluster.  Therefore the relevant
    ports should be opened on all units, which this class will do when
    it is wired up to a peer relation.

    """

    def __init__(self, charm, relation_name, prefix="port-manager"):
        super().__init__(charm, relation_name)
        self._prefix = prefix
        self.relation_name = relation_name

        self.framework.observe(charm.on[relation_name].relation_changed, self._on_relation_changed)

    def _on_relation_changed(self, event):
        ports = {
            pk.split('.')[1]: pv
            for pk, pv in event.relation.data[event.app].items()
            if pk.startswith(self._prefix + '.')
        }

        to_open = [pk for pk, pv in ports.items() if pv == 'open']
        for port in to_open:
            open_port(port)

        to_close = [pk for pk, pv in ports.items() if pv == 'close']
        for port in to_close:
            close_port(port)

    def _port_do(self, port, action):
        rels = self.model.relations[self.relation_name]
        app = self.model.unit.app
        for rel in rels:
            rel.data[app]['{}.{}'.format(self._prefix, port)] = action

    def open(self, port):
        """Open a port.  Must only be called by the leader unit."""
        self._port_do(port, 'open')

    def close(self, port):
        """Close a port.  Must only be called by the leader unit."""
        self._port_do(port, 'close')
