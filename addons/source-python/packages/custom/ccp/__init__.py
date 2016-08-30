from configparser import ConfigParser
from traceback import format_exc

from core import AutoUnload, echo_console
from paths import CUSTOM_DATA_PATH

from .sock_server import SockServer


CCP_DATA_PATH = CUSTOM_DATA_PATH / "ccp"
CONFIG_FILE = CCP_DATA_PATH / "config.ini"

OUT_BYTES_COMMUNICATION_ACCEPTED = b"\x01"
OUT_BYTES_NOBODY_HOME = b"\x02"
OUT_BYTES_COMMUNICATOR_ERROR = b"\x03"
IN_BYTES_COMMUNICATION_END = b"\x01"

config = ConfigParser()
config.read(CONFIG_FILE)

_communicator_callbacks = {}


def register_custom_communicator_callback(plugin_name, callback):
    if plugin_name in _communicator_callbacks:
        raise ValueError("'{}' plugin name is already bound to '{}'".format(
            plugin_name, _communicator_callbacks[plugin_name]))

    _communicator_callbacks[plugin_name] = callback


def unregister_custom_communicator_callback(plugin_name):
    del _communicator_callbacks[plugin_name]


class CustomCommunicator(AutoUnload):
    def __init__(self, plugin_name):
        self._plugin_name = plugin_name

    def __call__(self, callback):
        register_custom_communicator_callback(self._plugin_name, callback)
        return callback

    def _unload_instance(self):
        unregister_custom_communicator_callback(self._plugin_name)


class CCPClient:
    def __init__(self, sock_client):
        self.sock_client = sock_client

        self._plugin_name = None
        sock_client.message_receive_callback = self._message_receive_callback

    def _message_receive_callback(self, message):
        if self._plugin_name is None:
            try:
                self._plugin_name = message.decode('utf-8')
            except UnicodeDecodeError:
                self.sock_client.stop()

            if self._plugin_name in _communicator_callbacks:
                self.sock_client.send_message(OUT_BYTES_COMMUNICATION_ACCEPTED)
            else:
                self.sock_client.send_message(OUT_BYTES_NOBODY_HOME)

            return

        code, data = message[:1], message[1:]

        if code == IN_BYTES_COMMUNICATION_END:
            self.sock_client.stop()
            return

        if self._plugin_name in _communicator_callbacks:
            try:
                response = _communicator_callbacks[self._plugin_name](data)
            except Exception:
                echo_console(format_exc())
                self.sock_client.send_message(OUT_BYTES_COMMUNICATOR_ERROR)
                return

            self.sock_client.send_message(response)


server = None


def _client_accept_callback(sock_client):
    CCPClient(sock_client)


def restart_server():
    global server
    if server is not None:
        server.stop()

    server = SockServer(
        host=config['server']['host'],
        port=int(config['server']['port']),
        whitelist=config['server']['whitelist'].split(','),
        client_accept_callback=_client_accept_callback,
    )
    server.start()

restart_server()
