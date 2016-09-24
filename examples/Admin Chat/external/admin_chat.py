#!python3
from ccp.constants import CommunicationMode
from ccp.transmit import SRCDSClient


class TestPluginClient(SRCDSClient):
    def on_connected(self):
        print("Connection established, setting mode to REQUEST-BASED...")
        self.set_mode(CommunicationMode.REQUEST_BASED)

    def on_comm_accepted(self):
        self.prompt_message()

    def on_data_received(self, data):
        if data == b"OK":
            print("Message was delivered successfully!")
        else:
            print("Failed to deliver the message")

        self.prompt_message()

    def on_comm_error(self):
        print("Something went wrong on the other side...")

    def on_protocol_error(self):
        print("There was a misunderstanding between CCP package we use and "
              "CCP package SRCDS uses")

    def on_comm_end(self):
        print("Communication has ended without errors.")

    def on_nobody_home(self):
        print("Receiving plugin has been unloaded (or was not loaded at all)")

    def prompt_message(self):
        message = input("Enter the message (leave empty to quit): ")
        if not message:
            self.stop()

        else:
            self.send_data(message.encode('utf-8'))


test_plugin_client = TestPluginClient(('127.0.0.1', 28080), 'ccp_admin_chat')
test_plugin_client.start()
