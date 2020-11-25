from ops.charm import RelationEvent
from ops.framework import EventSource, Object, ObjectEvents, StoredState

from utils import open_port, close_port


class PortManagerEvent(RelationEvent):
    def __init__(self, handle, relation, app, unit, local_unit, port):
        super().__init__(handle, relation, app, unit)
        self._local_unit = local_unit
        self._port = port

    @property
    def port(self):
        """Retrieve requested port."""
        return self._port

    def snapshot(self):
        s = [
            super().snapshot(),
            dict(
                local_unit_name=self._local_unit.name,
                port=self._port,
            ),
        ]
        return s

    def restore(self, snapshot):
        sup, mine = snapshot
        super().restore(sup)
        self._local_unit = self.framework.model.get_unit(mine["local_unit_name"])
        self._port = mine['port']


class OpenPortEvent(PortManagerEvent):
    """A port is open."""


class ClosePortEvent(PortManagerEvent):
    """A port is closed."""


class PortManagerEvents(ObjectEvents):
    open_port = EventSource(OpenPortEvent)
    close_port = EventSource(ClosePortEvent)


class PortManager(Object):
    """Manage ports that must be in the same state on all units in the application.

    By wiring this class up to a peer relation, when the microk8s
    leader enables the ingress addon, it is enabled for all nodes in
    the cluster, and so all units should open the relevant ports.

    If PortManager is wired up to a normal relation, this application
    will manage the other application's ports.  However, bear in mind
    that the other application will be able to manage our ports too.

    (This is untested, but I'm pretty sure that's what would happen!)

    """
    on = PortManagerEvents()
    _state = StoredState()

    def __init__(self, charm, relation_name, prefix="port-manager"):
        super().__init__(charm, relation_name)
        self._prefix = prefix
        self.relation_name = relation_name

        self.framework.observe(charm.on[relation_name].relation_changed, self._on_relation_changed)
        self.framework.observe(self.on.open_port, self._on_open_port)
        self.framework.observe(self.on.close_port, self._on_close_port)

    def _event_args(self, relation_event, port):
        return dict(
            relation=relation_event.relation,
            app=relation_event.app,
            unit=relation_event.unit,
            local_unit=self.model.unit,
            port=port,
        )

    def _on_relation_changed(self, event):
        ports = {
            pk.split('.')[1]: pv
            for pk, pv in event.relation.data[event.app].items()
            if pk.startswith(self._prefix + '.')
        }

        to_open = [pk for pk, pv in ports.items() if pv == 'open']
        for port in to_open:
            self.on.open_port.emit(**self._event_args(event, port))

        to_close = [pk for pk, pv in ports.items() if pv == 'close']
        for port in to_close:
            self.on.close_port.emit(**self._event_args(event, port))

    def _on_open_port(self, event):
        open_port(event.port)

    def _on_close_port(self, event):
        close_port(event.port)

    def open_port(self, port):
        """Open a port.  Must only be called by the leader unit."""
        rels = self.model.relations[self.relation_name]
        app = self.model.unit.app
        for rel in rels:
            rel.data[app]['{}.{}'.format(self._prefix, port)] = 'open'

    def close_port(self, port):
        """Close a port.  Must only be called by the leader unit."""
        rels = self.model.relations[self.relation_name]
        app = self.model.unit.app
        for rel in rels:
            rel.data[app]['{}.{}'.format(self._prefix, port)] = 'close'
