# hotkey_daemon.py
import evdev
import socket
import os

SOCKET_PATH = "/tmp/hpsolver_hotkey.socket"
HOTKEY_CODE = 66  # F8

def main():
    # Remove old socket if exists
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass

    # Set up UNIX socket (server)
    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(SOCKET_PATH)
    server_sock.listen(1)
    print(f"Daemon listening on {SOCKET_PATH}...")

    # Accept a single client connection
    conn, _ = server_sock.accept()
    print("Listener connected.")

    # Find keyboard device (your selection code here)
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    kb = None
    for d in devices:
        if 'keyboard' in d.name.lower() or 'kbd' in d.name.lower():
            kb = d
            break
    if not kb:
        print("No keyboard device found.")
        return

    print(f"Listening for F8 on {kb.path}...")

    for event in kb.read_loop():
        if event.type == evdev.ecodes.EV_KEY and event.value == 1:  # key down
            if event.code == HOTKEY_CODE:
                print("F8 pressed, sending signal.")
                try:
                    conn.sendall(b"single_cell")
                except BrokenPipeError:
                    print("Listener disconnected.")
                    break

    conn.close()
    server_sock.close()

if __name__ == "__main__":
    main()
