import os
import Sources.input as input
import Sources.communications as communications
import time


input.start()
communications.start()

firstConnection = False
Connected = False

try:

    while True:
        command = input.get_input_from_terminal_if_ready(input.input_ready)
        if command is not None:
            communications.parse_command(command)

        if len(communications.pending_connections)>0:
            print(communications.pending_connections)
        if len(communications.open_connections) == 0:
            communications.parse_command("connect ettorecraft.ddns.net")
            time.sleep(1)

except KeyboardInterrupt:
    input.rprint("Exited Successfully",end="\n")
    os._exit(1)
