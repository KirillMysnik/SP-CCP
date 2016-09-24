from configparser import ConfigParser

from paths import CUSTOM_DATA_PATH

from .receive import CCPReceiveClient
from .sock_server import SockServer


CCP_DATA_PATH = CUSTOM_DATA_PATH / "ccp"
CONFIG_FILE = CCP_DATA_PATH / "config.ini"

config = ConfigParser()
config.read(CONFIG_FILE)

server = None


def _client_accept_callback(addr, sock_client):
    CCPReceiveClient(addr, sock_client)


def restart_server():
    global server
    if server is not None:
        server.stop()

    server = SockServer(
        addr=(config['server']['host'], int(config['server']['port'])),
        whitelist=config['server']['whitelist'].split(','),
        client_accept_callback=_client_accept_callback
    )
    server.start()

restart_server()
