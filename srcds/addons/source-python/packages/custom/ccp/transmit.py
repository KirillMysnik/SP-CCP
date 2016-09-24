import socket

from core import WeakAutoUnload
from listeners.tick import GameThread

from .constants import CommunicationMode
from .constants import IN_BYTES_COMM_END
from .constants import IN_BYTES_COMM_START_RAW
from .constants import IN_BYTES_COMM_START_REQUEST_BASED
from .constants import IN_BYTES_DATA
from .constants import OUT_BYTES_COMM_ACCEPTED
from .constants import OUT_BYTES_COMM_END
from .constants import OUT_BYTES_COMM_ERROR
from .constants import OUT_BYTES_DATA
from .constants import OUT_BYTES_NOBODY_HOME
from .constants import OUT_BYTES_PROTOCOL_ERROR
from .sock_client import SockClient


class SRCDSClient(WeakAutoUnload, GameThread):
    def __init__(self, addr, plugin_name, connection_error_callback=None,
                 comm_accepted_callback=None, nobody_home_callback=None,
                 comm_end_callback=None, protocol_error_callback=None,
                 comm_error_callback=None, data_received_callback=None,
                 connected_callback=None, connection_abort_callback=None):

        super().__init__()

        self.addr = addr
        self.plugin_name = plugin_name
        self._mode = CommunicationMode.UNDEFINED
        self._in_unload = False

        self._connection_error_callback = connection_error_callback
        self._comm_accepted_callback = comm_accepted_callback
        self._nobody_home_callback = nobody_home_callback
        self._comm_end_callback = comm_end_callback
        self._protocol_error_callback = protocol_error_callback
        self._comm_error_callback = comm_error_callback
        self._data_received_callback = data_received_callback
        self._connected_callback = connected_callback
        self._connection_abort_callback = connection_abort_callback

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock_client = None

    def run(self):
        if self._mode != CommunicationMode.UNDEFINED:
            raise ValueError("SRCDSClient instances can be only started once")

        self._mode = CommunicationMode.CONNECTING
        try:
            self.sock.connect(self.addr)

        except OSError:
            if self._in_unload:
                self._mode = CommunicationMode.ENDED
                return

            self.on_connection_error()

        else:
            if self._in_unload:
                self.sock.close()
                self._mode = CommunicationMode.ENDED
                return

            self._mode = CommunicationMode.CONNECTED

            self.sock_client = SockClient(
                None, self.sock, self._message_receive_callback,
                self.on_connection_abort, self.on_connection_abort)

            self.sock_client.start()

            self.on_connected()

    def on_connection_error(self):
        """Called when connection to the host didn't succeed."""
        if self._connection_error_callback is not None:
            self._connection_error_callback()

    def on_comm_accepted(self):
        """Called when communication mode / plugin name combination is
        accepted on the other side.
        """
        if self._comm_accepted_callback is not None:
            self._comm_accepted_callback()

    def on_nobody_home(self):
        """Called when the plugin name is not registered to handle this mode
        of communication or when the plugin gets unloaded during communication.
        """
        if self._nobody_home_callback is not None:
            self._nobody_home_callback()

    def on_comm_end(self):
        """Called when communication ends normally."""
        if self._comm_end_callback is not None:
            self._comm_end_callback()

    def on_protocol_error(self):
        """Called when the other side reports protocol incompatibility."""
        if self._protocol_error_callback is not None:
            self._protocol_error_callback()

    def on_comm_error(self):
        """Called when receiver callback fails to properly provide the data
        on the other side."""
        if self._comm_error_callback is not None:
            self._comm_error_callback()

    def on_data_received(self, data):
        """Called when the other side delivers data."""
        if self._data_received_callback is not None:
            self._data_received_callback(data)

    def on_connected(self):
        """Called when connection is successfully established
        (ready to set mode)."""
        if self._connected_callback is not None:
            self._connected_callback()

    def on_connection_abort(self):
        """Called when connection is closed or aborted unexpectedly."""
        if self._connection_abort_callback is not None:
            self._connection_abort_callback()

    def _message_receive_callback(self, message):
        if self._in_unload:
            return

        code, data = message[:1], message[1:]

        if code == OUT_BYTES_COMM_END:
            self._mode = CommunicationMode.ENDED
            self.sock_client.send_message(IN_BYTES_COMM_END)
            self.sock_client.stop()
            self.on_comm_end()
            return

        if code == OUT_BYTES_PROTOCOL_ERROR:
            self._mode = CommunicationMode.ERROR
            self.sock_client.stop()
            self.on_protocol_error()
            return

        if code == OUT_BYTES_COMM_ACCEPTED:
            try:
                self.on_comm_accepted()
            except:
                self._mode = CommunicationMode.ENDED
                self.sock_client.send_message(IN_BYTES_COMM_END)
                self.sock_client.stop()
                raise

            return

        if code == OUT_BYTES_NOBODY_HOME:
            self._mode = CommunicationMode.ENDED
            self.sock_client.send_message(IN_BYTES_COMM_END)
            self.sock_client.stop()
            self.on_nobody_home()
            return

        if code == OUT_BYTES_COMM_ERROR:
            self._mode = CommunicationMode.ENDED
            self.sock_client.send_message(IN_BYTES_COMM_END)
            self.sock_client.stop()
            self.on_comm_error()
            return

        if code == OUT_BYTES_DATA:
            try:
                self.on_data_received(data)
            except:
                self._mode = CommunicationMode.ENDED
                self.sock_client.send_message(IN_BYTES_COMM_END)
                self.sock_client.stop()
                raise

            return

    def set_mode(self, mode):
        if self._mode != CommunicationMode.CONNECTED:
            raise ValueError(
                "Communication mode can only be set once and cannot be set "
                "before connection has been established")

        if mode not in (
                CommunicationMode.REQUEST_BASED, CommunicationMode.RAW):

            raise ValueError(
                "Communication mode should be set either to "
                "CommunicationMode.REQUEST_BASED or CommunicationMode.RAW")

        self._mode = mode
        plugin_name = self.plugin_name.encode('utf-8')
        if mode == CommunicationMode.REQUEST_BASED:
            self.sock_client.send_message(
                IN_BYTES_COMM_START_REQUEST_BASED + plugin_name)

        else:
            self.sock_client.send_message(
                IN_BYTES_COMM_START_RAW + plugin_name)

    def send_data(self, data):
        if self._mode not in (
                CommunicationMode.REQUEST_BASED, CommunicationMode.RAW):

            raise ValueError(
                "send_data can only be called if the communication mode is "
                "set to either CommunicationMode.REQUEST_BASED or "
                "CommunicationMode.RAW")

        if not isinstance(data, bytes):
            if isinstance(data, str):
                data = data.encode('utf-8')
            else:
                raise ValueError("send_data only accepts bytes or str values")

        self.sock_client.send_message(IN_BYTES_DATA + data)

    def stop(self):
        if self._mode not in (
                CommunicationMode.REQUEST_BASED, CommunicationMode.RAW):

            raise ValueError(
                "stop can only be called if the communication mode is "
                "set to either CommunicationMode.REQUEST_BASED or "
                "CommunicationMode.RAW")

        self._mode = CommunicationMode.ENDED
        self.sock_client.send_message(IN_BYTES_COMM_END)
        self.sock_client.stop()
        self.on_comm_end()

    def _unload_instance(self):
        self._in_unload = True

        if self._mode in (CommunicationMode.ENDED, CommunicationMode.ERROR):
            return

        if self._mode in (
                CommunicationMode.REQUEST_BASED, CommunicationMode.RAW):

            self._mode = CommunicationMode.ENDED
            self.sock_client.send_message(IN_BYTES_COMM_END)
            self.sock_client.stop()
            return

        if self._mode in (
                CommunicationMode.UNDEFINED,
                CommunicationMode.CONNECTED,
                CommunicationMode.CONNECTING,
        ):

            self._mode = CommunicationMode.ENDED
            return
