from core import AutoUnload, WeakAutoUnload
from listeners import OnPluginUnloaded

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


_request_based_receiver_callbacks = {}
_raw_receiver_classes = {}


def register_request_based_receiver_callback(plugin_name, callback):
    if plugin_name in _request_based_receiver_callbacks:
        raise ValueError(
            "'{}' is already bound to handle request-based communication with "
            "plugin '{}'".format(
                _request_based_receiver_callbacks[plugin_name],
                plugin_name
            )
        )

    _request_based_receiver_callbacks[plugin_name] = callback


def unregister_request_based_receiver_callback(plugin_name):
    del _request_based_receiver_callbacks[plugin_name]


class RequestBasedReceiver(AutoUnload):
    def __init__(self, plugin_name):
        self._plugin_name = plugin_name

    def __call__(self, callback):
        register_request_based_receiver_callback(
            self._plugin_name, callback)

        return callback

    def _unload_instance(self):
        unregister_request_based_receiver_callback(self._plugin_name)


class RawReceiverMeta(type):
    def __init__(cls, name, bases, namespace):
        super().__init__(name, bases, namespace)

        if namespace.get('abstract', False):
            del cls.abstract
            return

        if not hasattr(cls, 'plugin_name'):
            raise ValueError("Class '{}' doesn't have 'plugin_name' attribute")

        if cls.plugin_name in _raw_receiver_classes:
            raise ValueError(
                "'{}' is already bound to handle raw communication with "
                "plugin '{}'".format(
                    _raw_receiver_classes[cls.plugin_name], cls.plugin_name))

        _raw_receiver_classes[cls.plugin_name] = cls


class RawReceiver(WeakAutoUnload, metaclass=RawReceiverMeta):
    abstract = True

    def __init__(self, addr, ccp_receive_client):
        self.addr = addr
        self.send_data = ccp_receive_client.raw_send_data
        self.stop = ccp_receive_client.raw_stop
        self._unload = ccp_receive_client.raw_unload

    def _unload_instance(self):
        self._unload()

    def on_data_received(self, data):
        return NotImplemented

    def on_connection_abort(self):
        return NotImplemented


class CCPReceiveClient:
    def __init__(self, addr, sock_client):
        self.addr = addr
        self.sock_client = sock_client

        self._plugin_name = None
        self._raw_receiver = None
        self._mode = CommunicationMode.UNDEFINED

        sock_client._message_receive_callback = self.on_message_receive
        sock_client._connection_close_callback = self.on_connection_abort
        sock_client._connection_abort_callback = self.on_connection_abort

    def on_message_receive(self, message):
        code, data = message[:1], message[1:]

        if code == IN_BYTES_COMM_END:
            self._raw_receiver = None
            self._mode = CommunicationMode.ENDED
            self.sock_client.stop()
            return

        if self._mode == CommunicationMode.END_REQUEST_SENT:
            self._raw_receiver = None
            self._mode = CommunicationMode.ERROR
            self.sock_client.send_message(OUT_BYTES_PROTOCOL_ERROR)
            self.sock_client.stop()
            return

        if code in (
                IN_BYTES_COMM_START_REQUEST_BASED, IN_BYTES_COMM_START_RAW):

            if self._mode != CommunicationMode.UNDEFINED:
                self._raw_receiver = None
                self._mode = CommunicationMode.ERROR
                self.sock_client.send_message(OUT_BYTES_PROTOCOL_ERROR)
                self.sock_client.stop()

            else:
                try:
                    self._plugin_name = data.decode('utf-8')
                except UnicodeDecodeError:
                    self._mode = CommunicationMode.ERROR
                    self.sock_client.send(OUT_BYTES_PROTOCOL_ERROR)
                    self.sock_client.stop()
                    return

                if code == IN_BYTES_COMM_START_REQUEST_BASED:
                    if self._plugin_name in _request_based_receiver_callbacks:
                        self._mode = CommunicationMode.REQUEST_BASED
                        self.sock_client.send_message(OUT_BYTES_COMM_ACCEPTED)

                    else:
                        self._mode = CommunicationMode.END_REQUEST_SENT
                        self.sock_client.send_message(OUT_BYTES_NOBODY_HOME)

                else:
                    if self._plugin_name in _raw_receiver_classes:
                        self._mode = CommunicationMode.RAW
                        raw_receiver_class = _raw_receiver_classes[
                            self._plugin_name]

                        try:
                            self._raw_receiver = raw_receiver_class(
                                self.addr[:], self)
                        except:
                            self._mode = CommunicationMode.END_REQUEST_SENT
                            self.sock_client.send_message(OUT_BYTES_COMM_ERROR)
                            raise

                        self.sock_client.send_message(OUT_BYTES_COMM_ACCEPTED)

                    else:
                        self._mode = CommunicationMode.END_REQUEST_SENT
                        self.sock_client.send_message(OUT_BYTES_NOBODY_HOME)

            return

        if code == IN_BYTES_DATA:
            if self._mode == CommunicationMode.REQUEST_BASED:

                # Check if plugin has been unloaded by now
                if self._plugin_name not in _request_based_receiver_callbacks:
                    self._mode = CommunicationMode.END_REQUEST_SENT
                    self.sock_client.send_message(OUT_BYTES_NOBODY_HOME)
                    return

                try:
                    response = _request_based_receiver_callbacks[
                        self._plugin_name](self.addr[:], data)

                    if not isinstance(response, bytes):
                        if isinstance(response, str):
                            response = response.encode('utf-8')
                        else:
                            raise ValueError(
                                "RequestBasedReceiver callback should "
                                "only return bytes or str values")

                except:
                    self._mode = CommunicationMode.END_REQUEST_SENT
                    self.sock_client.send_message(OUT_BYTES_COMM_ERROR)
                    raise

                self.sock_client.send_message(OUT_BYTES_DATA + response)

            elif self._mode == CommunicationMode.RAW:
                self._raw_receiver.on_data_received(data)

    def on_connection_abort(self):
        if self._mode != CommunicationMode.RAW:
            return

        try:
            self._raw_receiver.on_connection_abort()
        finally:
            self._raw_receiver = None
            self._mode = CommunicationMode.ENDED

    def raw_unload(self):
        if self._mode != CommunicationMode.RAW:
            raise ValueError(
                "raw_unload can only be called if the communication mode "
                "is set to CommunicationMode.RAW")

        self._raw_receiver = None
        self._mode = CommunicationMode.END_REQUEST_SENT
        self.sock_client.send_message(OUT_BYTES_NOBODY_HOME)

    def raw_stop(self):
        if self._mode != CommunicationMode.RAW:
            raise ValueError(
                "raw_stop can only be called if the communication mode "
                "is set to CommunicationMode.RAW")

        self._raw_receiver = None
        self._mode = CommunicationMode.END_REQUEST_SENT
        self.sock_client.send_message(OUT_BYTES_COMM_END)

    def raw_send_data(self, data):
        if self._mode != CommunicationMode.RAW:
            raise ValueError(
                "raw_send_data can only be called if the communication mode "
                "is set to CommunicationMode.RAW")

        if not isinstance(data, bytes):
            if isinstance(data, str):
                data = data.encode('utf-8')
            else:
                self._mode = CommunicationMode.END_REQUEST_SENT
                self.sock_client.send_message(OUT_BYTES_COMM_ERROR)
                raise ValueError("raw_send_data only accepts bytes or str "
                                 "values")

        self.sock_client.send_message(OUT_BYTES_DATA + data)


@OnPluginUnloaded
def listener_on_plugin_unloaded(plugin_name):
    _raw_receiver_classes.pop(plugin_name, None)
