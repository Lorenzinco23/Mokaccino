import os
import queue
import socket
from sqlite3 import Time
import threading
import json
import upnpy
from . import input
import datetime
import time

with open("config.json") as config_file:
    config = json.load(config_file)

PORT = config["port"]
ADDRESS = config["server"]
TIMEOUT = .1
USERNAME = config["nickname"]

'''
    HOST 1               HOST 2
    ----------------------------------
    CONNECT:23232   ->
                      <- HANDSHAKE:xyz
    CONNECTED:xyz   ->
    ----------------------------------
'''

open_connections:dict[str,tuple[str,int]] = {}
pending_connections:dict[str,tuple[str,int]] = {}
msg_queue:dict[tuple[str,int],queue.Queue[str]] = {}
pinged_peers:dict[tuple[str,int],int] = {}

udp_socket = socket.socket(family=socket.AF_INET,type=socket.SOCK_DGRAM)
udp_socket.settimeout(TIMEOUT)
udp_socket.bind(("0.0.0.0",PORT))

downstream_mutex = threading.Semaphore(1)

upnp = upnpy.UPnP()
devices = upnp.discover()
device = upnp.get_igd()
service = None
for s in device.get_services():
    for action in s.get_actions():
        if action.name == "AddPortMapping":
            service = s
            break
    if service is not None:
        break
#print(service.get_actions())

def string_to_address(address:str):
    address = address.strip("()")
    ip = address.split(",")[0].strip("\'")
    port = int(address.split(",")[1].strip())
    return (ip,port)

def parse_command(line:str):
    cmd = line.split()
    cmd[0]=cmd[0].lower()

    if cmd[0]=="request":
        searchuser(cmd[1])

    elif cmd[0] == "msg":
        msg_usr(line[len(cmd[1])+5:],open_connections[cmd[1]])

    elif cmd[0] == "ping":
        send("ping ",open_connections[cmd[1]])

    elif cmd[0] == "quit":
        open_connections.pop(cmd[1])

    elif cmd[0] == "info":
        input.rprint(open_connections[cmd[1]])

    elif cmd[0] == "connect":
        send(f"connect {cmd[1]}",(cmd[1],23232))

    elif cmd[0] == "help":
        input.rprint("CommandList:")
        input.rprint("request <user>        | asks the database for users IP and establishes connection")
        input.rprint("msg <user> <content>  | sends <content> to <user>")
        input.rprint("ping <user>           | calculates ping from you and <user>")
        input.rprint("quit <user>           | closes connection to <user>")
        input.rprint("connect <IP>          | connects to <IP>")
        input.rprint("info                  | displays all active connections")
        pass

def parse_stream(line:str,src:tuple[str,int]):
    cmd = line.split()
    cmd[0] = cmd[0].lower()

    if cmd[0] == "connect" and config["autoconnect"]:
        send(f"handshake {USERNAME}",src)
        pending_connections[cmd[1]] = src
    
    elif cmd[0] == "connect" and not config["autoconnect"]:
        input.rprint(f"User {src} wants to connect, to accept: type in | handshake {src[0]}")

    elif cmd[0] == "handshake":
        if cmd[1] in pending_connections:
            send("connected",src)
            msg_usr("Hi!",src)
        else: pass
    elif cmd[0] == "connected":
        if cmd[1] in pending_connections:
            open_connections[cmd[1]] = pending_connections[cmd[1]]
        pending_connections.pop(cmd[1])
    elif cmd[0] == "ping":
        if cmd[1] in open_connections:
            pong(open_connections[cmd[1]])
    elif cmd[0] == "pong":
        if cmd[1] in open_connections:
            input.rprint(f"pong! {pinged_peers[cmd[1]]}")
    elif cmd[0] == "msg":
        if cmd[1] in pending_connections:
            input.rprint(f"[{cmd[1]}][{cmd[2]}]:{line[len(cmd[1])+len(cmd[2])+5:]}") 

def msg_usr(msg:str,dest:tuple[str,int]):
    send(f"msg {USERNAME} {datetime.now()} {msg}",dest)

def ping(dest:tuple[str,int]):
    pinged_peers[dest] = int(time.time())*1000
    send(f"ping {USERNAME}",dest)

def pong(dest:tuple[str,int]):
    send(f"pong {USERNAME}",dest)

def send(message:str,dest:tuple[str,int]):
    global udp_socket
    global USERNAME
    udp_socket.sendto(message.encode("ASCII"),dest)

def searchuser(user):
    send(f"REQUEST {user} {USERNAME}")
    input.rprint("Search request sent, waiting for response...")

def receive():
    try:
        global msg_queue
        global udp_socket
        global open_connections
        while True:
            try:
                msg,addr = udp_socket.recvfrom(2048)
                
                #downstream_mutex.acquire()
                input.rprint(f"Received: {msg.decode('ASCII')} from {addr}")
                parse_stream(msg.decode("ASCII"),addr)
                #downstream_mutex.release()
            except TimeoutError:
                pass
            
    except KeyboardInterrupt:
        pass

def start():
    '''service.AddPortMapping(
        NewRemoteHost="",
        NewExternalPort=config["port"],
        NewProtocol="UDP",
        NewInternalPort=config["port"],
        NewInternalClient="1.1.1.1",
        NewEnabled=1,
        NewPortMappingDescription='Mokaccino',
        NewLeaseDuration=""
    )'''
    downstream = threading.Thread(target=receive)
    downstream.start()