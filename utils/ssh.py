import time

def run_ssh_command(host, username, password, commands, port=22, timeout=15):
    """
    Connects to a network device via SSH using paramiko and executes commands in an interactive shell.
    Sends paging-disable commands and collects the resulting output.
    
    :param host: Target hostname or IP
    :param username: SSH username
    :param password: SSH password
    :param commands: List of command strings to execute (or a single command string)
    :param port: SSH port (default: 22)
    :param timeout: Connection & read timeout in seconds (default: 15)
    :return: Full output string received from the session
    """
    try:
        import paramiko
    except ImportError:
        raise ImportError("paramiko is required for SSH connections. Please install it with 'pip install paramiko'.")

    if isinstance(commands, str):
        commands = [commands]

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=timeout,
            look_for_keys=False,
            allow_agent=False
        )

        shell = client.invoke_shell(term="vt100", width=200, height=500)
        shell.settimeout(timeout)

        # Allow initial banner / prompt to settle
        time.sleep(1.5)
        initial_out = ""
        while shell.recv_ready():
            initial_out += shell.recv(4096).decode("utf-8", errors="ignore")

        # Disable terminal paging
        shell.send("no page\n")
        time.sleep(0.5)

        full_output = initial_out
        for cmd in commands:
            shell.send(f"{cmd}\n")
            time.sleep(1)

        # Read until quiet or timeout
        start_time = time.time()
        while time.time() - start_time < timeout:
            if shell.recv_ready():
                chunk = shell.recv(8192).decode("utf-8", errors="ignore")
                full_output += chunk
                # Small pause to see if more is arriving
                time.sleep(0.3)
                if not shell.recv_ready():
                    # If we got a command prompt end (# or >), we can break early
                    if full_output.strip().endswith(("#", ">")):
                        break
            else:
                time.sleep(0.5)

        shell.send("exit\n")
        return full_output
    finally:
        client.close()
