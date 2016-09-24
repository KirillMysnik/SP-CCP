from select import select
import socket
from threading import Thread

from .sock_client import SockClient


class SockServer(Thread):
    def __init__(self, addr, whitelist=(), client_accept_callback=None):
        super().__init__()

        self.running = False
        self.clients = []
        self.whitelist = whitelist
        self.client_accept_callback = client_accept_callback

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(addr)

    def remove_client(self, client):
        self.clients.remove(client)

    def run(self):
        self.running = True
        self.sock.listen()

        r, w, e = select([self.sock], [], [])
        while self.running:
            if self.sock in r:
                client_sock, addr = self.sock.accept()

                if addr[0] not in self.whitelist:
                    client_sock.close()
                    continue

                client = SockClient(self, client_sock)
                self.clients.append(client)
                self.on_client_accept(addr, client)

                client.start()

            r, w, e = select([self.sock], [], [])

    def stop(self):
        if not self.running:
            return

        self.running = False
        for client in self.clients:
            client.stop()

        self.sock.close()

    def on_client_accept(self, addr, client):
        if self.client_accept_callback is not None:
            self.client_accept_callback(addr, client)
