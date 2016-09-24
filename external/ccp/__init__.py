#from .receive import CCPReceiveClient
from .sock_server import SockServer


server = None


def _client_accept_callback(addr, sock_client):
    #CCPReceiveClient(addr, sock_client)
    pass


def restart_server(addr, whitelist):
    global server
    if server is not None:
        server.stop()

    server = SockServer(addr, whitelist, _client_accept_callback)
    server.start()
