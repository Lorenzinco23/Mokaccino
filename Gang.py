import queue
import socket
import json
import sys
import threading
import time
from typing import Callable

'''
A peer must send "CONNECT:<nickname>" to try to connect to another peer with UDP
each peer must respond with "HANDSHAKE:<nickname>" after the first CONNECT message received
the first peer must send "CONNECTED:<nickname>" after the handshake is received
'''

TIMEOUT = 0.1
CONNECTION_ATTEMPTS = 5

with open("config.json") as config_file:
    config = json.load(config_file)

def rprint(string,end="\n> "):
    print("\r"+string,end=end)

local_address = ("0.0.0.0",25567)
if len(sys.argv)>1:
    server_address = (sys.argv[1],25566)
else:
    server_address = (config["server"],25566)

server_connected = False

open_connections:dict[str,tuple[str,int]] = {}
pending_connections:queue.Queue[tuple[str,tuple[str,int],int]] = queue.Queue()
waiting_handshake_connections:dict[str,tuple[str,int]] = {}
waiting_connected_connections:dict[str,tuple[str,int]] = {}

def string_to_address(address:str):
    address = address.strip("()")
    ip = address.split(",")[0].strip("\'")
    port = int(address.split(",")[1].strip())
    return (ip,port)

def new_server_socket():
    global server_connected
    server = socket.socket(family=socket.AF_INET,type=socket.SOCK_STREAM)    
    server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    server.settimeout(TIMEOUT)
    server.connect(server_address)
    server.send(config["nickname"].encode("ASCII"))
    return server

udp_socket = socket.socket(family=socket.AF_INET,type=socket.SOCK_DGRAM)
udp_socket.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
udp_socket.bind(local_address)


udp_socket.settimeout(TIMEOUT)

while server_connected == False:
    try:
        server = new_server_socket()
        server_connected = True
        print("Connected!")
    except socket.timeout:
        pass

command_buffer = ""
def terminal(input_ready:threading.Event):
    global command_buffer
    try:
        while True:
            if not input_ready.is_set():
                command = input("> ")
                command_buffer = command
                input_ready.set()
    except (KeyboardInterrupt,EOFError):
        pass

input_ready = threading.Event()
input_mutex = threading.Semaphore(1)
terminal_thread = threading.Thread(target=terminal,args=(input_ready,))
terminal_thread.start()

def get_input_from_terminal(input_ready:threading.Event):
    global command_buffer
    global input_mutex
    input_mutex.acquire()
    input_ready.wait()
    ret = command_buffer
    input_ready.clear()
    input_mutex.release()
    return ret

def get_input_from_terminal_if_ready(input_ready:threading.Event):
    global command_buffer
    global input_mutex
    input_mutex.acquire()
    if input_ready.is_set():
        ret = command_buffer
        input_ready.clear()
        input_mutex.release()
        return ret
    else:
        input_mutex.release()
        return None

def get_input_from_terminal_with_timeout(input_ready:threading.Event,timeout):
    global command_buffer
    global input_mutex
    begin = time.time()
    input_mutex.acquire()
    while time.time()-begin < timeout:
        if input_ready.is_set():
            ret = command_buffer
            input_ready.clear()
            input_mutex.release()
            return ret
    input_mutex.release()
    return None

class InputTask(threading.Thread):
    input_task_mutex = threading.Semaphore(1)
    def __init__(self,pre_task:Callable,task:Callable[[str],None]):
        threading.Thread.__init__(self)
        self.pre_task = pre_task
        self.task = task
    def run(self):
        global command_buffer
        global input_mutex
        global input_ready
        InputTask.input_task_mutex.acquire()
        self.pre_task()
        self.task(get_input_from_terminal(input_ready))
        InputTask.input_task_mutex.release()

def connection(input_ready:threading.Event):
    global terminal_thread
    global server
    global server_connected
    global open_connections
    global waiting_handshake_connections
    global waiting_connected_connections
    global pending_connections
    try:
        while True:
            #check commands from server
            if server_connected:
                try:
                    data = server.recv(1024)
                    if not data:
                        server.close()
                        server_connected = False
                        rprint("\033[31mServer disconnected!\033[0m")
                    else:
                        command = data.decode("ASCII").split(":")[0]
                        
                        if command == "PENDING":
                            if "autoaccept" in config and config["autoaccept"]:
                                udp_socket.sendto(f"HERE:{config['nickname']}".encode("ASCII"),server_address)
                            else:
                                def pre_input_task():
                                    rprint(f"Accept connection from {data.decode('ASCII').split(':')[1]}? (y/N): ", end="")
                                def input_task_function(res):
                                    if res == 'Y' or res == 'y':
                                        udp_socket.sendto(f"HERE:{config['nickname']}".encode("ASCII"),server_address)
                                    else:
                                        udp_socket.sendto(f"REFUSE:{config['nickname']}".encode("ASCII"),server_address)
                                input_task = InputTask(pre_input_task,input_task_function)
                                input_task.start()
                        elif command == "FOUND":
                            target_nickname = data.decode("ASCII").split(":")[1]
                            address = string_to_address(data.decode("ASCII").split(":")[2])
                            rprint(f"{target_nickname} found at {address}")

                            pending_connections.put((target_nickname,address,0),block=False)                                    
                                

                        elif command == "NOT FOUND":
                            target_nickname = data.decode("ASCII").split(":")[1]
                            rprint(f"{target_nickname} not found")
                except socket.timeout:
                    pass   
            else:
                try:
                    server = new_server_socket()
                    server_connected = True
                    rprint("\033[32mServer reconnected!\033[0m")
                except (socket.timeout, ConnectionRefusedError):
                    pass
            
            try:
                msg,addr = udp_socket.recvfrom(1024)
                rprint(f"{addr}: {msg.decode('ASCII')}")
                decoded_msg = msg.decode("ASCII").split(":")
                if decoded_msg[0] == "CONNECT":
                    pending_connections.put((decoded_msg[1],addr,1),block=False)
                elif decoded_msg[0] == "HANDSHAKE":
                    if decoded_msg[1] in waiting_handshake_connections and waiting_handshake_connections[decoded_msg[1]]==addr:
                        waiting_handshake_connections.pop(decoded_msg[1])
                        pending_connections.put((decoded_msg[1],addr,2),block=False)
                elif decoded_msg[0] == "CONNECTED":
                    if decoded_msg[1] in waiting_connected_connections and waiting_connected_connections[decoded_msg[1]]==addr:
                        waiting_connected_connections.pop(decoded_msg[1])
                        open_connections[decoded_msg[1]] = address
                        rprint(f"Connected with {decoded_msg[1]}")
            except TimeoutError:
                pass

            fallback_wating_handshake:dict[str,tuple(str,int)] = {}
            fallback_wating_connected:dict[str,tuple(str,int)] = {}
            for nickname,failed_connection in waiting_handshake_connections.items():
                fallback_wating_handshake[nickname] = (failed_connection[0],failed_connection[1]+1)
            for nickname,new_addr in fallback_wating_handshake.items():
                waiting_handshake_connections[nickname]=new_addr
            for nickname,failed_connection in waiting_connected_connections.items():
                fallback_wating_connected[nickname] = (failed_connection[0],failed_connection[1]+1)
            for nickname,new_addr in fallback_wating_connected.items():
                waiting_connected_connections[nickname]=new_addr


            while not pending_connections.empty():
                target_nickname,address,stage = pending_connections.get(block=False)
                if stage==0: #->[CONNECT] HANDSHAKE CONNECTED
                    udp_socket.sendto(f"CONNECT:{config['nickname']}".encode("ASCII"),address)
                    waiting_handshake_connections[target_nickname] = address
                elif stage==1: #CONNECT ->[HANDSHAKE] CONNECTED
                    udp_socket.sendto(f"HANDSHAKE:{config['nickname']}".encode("ASCII"),address)
                    waiting_connected_connections[target_nickname] = address
                elif stage==2: #CONNECT HANDSHAKE ->[CONNECTED]
                    udp_socket.sendto(f"CONNECTED:{config['nickname']}".encode("ASCII"),address)
                    open_connections[target_nickname] = address
                    rprint(f"Connected with {decoded_msg[1]}")



            if not terminal_thread.is_alive():
                break
            else:
                input = get_input_from_terminal_if_ready(input_ready)
                if input is not None:#handle input
                    udp_socket.sendto(input.encode("ASCII"),server_address)
    except KeyboardInterrupt:
        pass
    server.close()
    rprint("Disconnected!",end="")

connection_thread = threading.Thread(target=connection,args=(input_ready,))
connection_thread.start()

try:
    connection_thread.join()
    terminal_thread.join()
except KeyboardInterrupt:
    pass