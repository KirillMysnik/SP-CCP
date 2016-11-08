from select import select

from listeners.tick import GameThread


CHUNK_SIZE = 4096
LENGTH_BYTES = 3


class ConnectionClose(OSError):
    pass


class AsyncSockClient(GameThread):
    def __init__(self, sock_server, sock, message_receive_callback=None,
                 connection_abort_callback=None,
                 connection_close_callback=None):

        super().__init__()

        self._sock_server = sock_server
        self.sock = sock
        self._message_receive_callback = message_receive_callback
        self._connection_abort_callback = connection_abort_callback
        self._connection_close_callback = connection_close_callback

        self.running = False

    def _read_sock(self, length):
        data = b''
        while len(data) < length:
            chunk = self.sock.recv(min(CHUNK_SIZE, length - len(data)))
            if chunk == b'':
                self.stop()
                return None

            data += chunk

        return data

    def _write_sock(self, data):
        total_sent = 0
        while total_sent < len(data):
            sent = self.sock.send(data[total_sent:])
            if sent == 0:
                self.stop()
                raise ConnectionClose("Sent zero bytes")

            total_sent += sent

    def receive_message(self):
        # Parse message length - first LENGTH_BYTES bytes
        length_bytes = self._read_sock(LENGTH_BYTES)
        if length_bytes is None:
            return None

        length = int.from_bytes(length_bytes, byteorder='big')

        # Receive the message
        message = self._read_sock(length)
        return message

    def send_message(self, message):
        length = len(message)
        length_bytes = length.to_bytes(LENGTH_BYTES, byteorder='big')
        self._write_sock(length_bytes + message)

    def run(self):
        self.running = True

        r, w, e = select([self.sock], [], [])
        while self.running:
            if self.sock in r:
                try:
                    message = self.receive_message()
                except OSError:
                    self.stop()
                    self.on_connection_abort()
                else:
                    if message is None:
                        self.stop()
                        self.on_connection_close()

                    else:
                        self.on_message_receive(message)

            if self.running:
                r, w, e = select([self.sock], [], [])

    def stop(self):
        if not self.running:
            return

        if self._sock_server is not None:
            self._sock_server.remove_client(self)

        self.running = False

        self.sock.close()

    def on_message_receive(self, message):
        if self._message_receive_callback is not None:
            self._message_receive_callback(message)

    def on_connection_abort(self):
        if self._connection_abort_callback is not None:
            self._connection_abort_callback()

    def on_connection_close(self):
        if self._connection_close_callback is not None:
            self._connection_close_callback()
