import threading
import time
from typing import Callable
from . import communications


def rprint(string,end="\n> "):
    print("\r"+string,end=end)



def string_to_address(address:str):
    address = address.strip("()")
    ip = address.split(",")[0].strip("\'")
    port = int(address.split(",")[1].strip())
    return (ip,port)


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

def start():
    global terminal_thread
    terminal_thread = threading.Thread(target=terminal,args=(input_ready,))
    terminal_thread.start()