import os
import Sources.input as input
import Sources.communications as communications


input.start()
communications.start()

firstConnection = False
Connected = False

try:

    while True:
        command = input.get_input_from_terminal_if_ready(input.input_ready)
        if command is not None:
            communications.parse_command(command)
        if len(communications.open_connections) == 0:
            communications.parse_command("connect ettorecraft.ddns.net")

except KeyboardInterrupt:
    input.rprint("Exited Successfully",end="\n")
    os._exit(1)
