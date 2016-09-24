from colors import RED, WHITE
from messages import SayText2

from ccp.receive import RequestBasedReceiver


@RequestBasedReceiver('ccp_admin_chat')
def ccp_admin_chat_receiver(addr, data):
    SayText2("{color1}ADMIN: {color2}{message}".format(
        color1=RED,
        color2=WHITE,
        message=data.decode('utf-8')
    )).send()
    return "OK"
