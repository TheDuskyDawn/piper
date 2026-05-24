#!/usr/bin/env python3
"""Automated Piper TTS and Speech Dispatcher installer/configurator.

This script sets up Piper TTS, downloads the high-quality hfc_female voice,
configures a persistent Unix-socket-based Piper daemon, integrates it with
Speech Dispatcher, and enables auto-start via a systemd user service—all
without requiring sudo or root privileges.
"""

import os
import shutil
import subprocess
import sys
import urllib.request
from typing import Optional

# Configurable paths
BASE_DIR = os.path.expanduser("~/.local/share/piper-voices")
BIN_DIR = os.path.expanduser("~/.local/bin")
CONFIG_DIR = os.path.expanduser("~/.config/speech-dispatcher")
MODULES_DIR = os.path.join(CONFIG_DIR, "modules")
SYSTEMD_DIR = os.path.expanduser("~/.config/systemd/user")
VENV_DIR = os.path.expanduser("~/.local/share/piper-venv")

VOICE_ONNX_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx"
VOICE_JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx.json"


def log(message: str) -> None:
    """Print a progress message to stderr."""
    print(f"[*] {message}", file=sys.stderr, flush=True)


def download_file(url: str, dest: str) -> None:
    """Download a file from a URL to a local destination path.

    Args:
        url: The remote URL.
        dest: The local path to save the file.
    """
    log(f"Downloading {url} to {dest}...")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    urllib.request.urlretrieve(url, dest)


def setup_piper_venv() -> str:
    """Sets up a virtual environment and installs piper-tts.

    Returns:
        The absolute path to the installed python executable inside the venv.
    """
    log("Setting up Python virtual environment for Piper...")
    os.makedirs(os.path.dirname(VENV_DIR), exist_ok=True)

    # Create venv
    subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)
    venv_python = os.path.join(VENV_DIR, "bin", "python")
    venv_pip = os.path.join(VENV_DIR, "bin", "pip")

    # Install/upgrade pip and install piper-tts
    log("Installing piper-tts inside venv...")
    subprocess.run([venv_pip, "install", "--upgrade", "pip"], check=True)
    subprocess.run([venv_pip, "install", "piper-tts"], check=True)

    return venv_python


def main() -> None:
    """Main execution function to orchestrate the entire setup."""
    os.makedirs(BASE_DIR, exist_ok=True)
    os.makedirs(BIN_DIR, exist_ok=True)
    os.makedirs(MODULES_DIR, exist_ok=True)
    os.makedirs(SYSTEMD_DIR, exist_ok=True)

    # 1. Install Piper TTS in venv
    venv_python = setup_piper_venv()

    # 2. Download Voices
    model_path = os.path.join(BASE_DIR, "en_US-hfc_female-medium.onnx")
    json_path = model_path + ".json"
    if not os.path.exists(model_path):
        download_file(VOICE_ONNX_URL, model_path)
    if not os.path.exists(json_path):
        download_file(VOICE_JSON_URL, json_path)

    # 3. Create piper-server.py
    server_script_path = os.path.join(BASE_DIR, "piper-server.py")
    log(f"Writing {server_script_path}...")
    with open(server_script_path, "w", encoding="utf-8") as f:
        f.write('''#!/usr/bin/env python3
"""Piper TTS server — keeps model loaded for instant synthesis."""

import os
import socket
import sys
import numpy as np

SOCKET_PATH = os.path.expanduser("~/.cache/piper-server.sock")

def run_server(model_path: str) -> None:
    from piper import PiperVoice

    print(f"Loading model: {model_path}", file=sys.stderr, flush=True)
    voice = PiperVoice.load(model_path)
    sample_rate = voice.config.sample_rate
    print(f"Model loaded. Listening on {SOCKET_PATH}", file=sys.stderr, flush=True)

    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_PATH)
    sock.listen(5)
    os.chmod(SOCKET_PATH, 0o600)

    while True:
        conn, _ = sock.accept()
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk

            text = data.decode("utf-8").strip()
            if not text:
                continue

            for audio_chunk in voice.synthesize(text):
                pcm = (audio_chunk.audio_float_array * 32767).astype(np.int16).tobytes()
                conn.sendall(pcm)
        except BrokenPipeError:
            pass
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr, flush=True)
        finally:
            try:
                conn.close()
            except OSError:
                pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <model.onnx>", file=sys.stderr)
        sys.exit(1)
    run_server(sys.argv[1])
''')
    os.chmod(server_script_path, 0o755)

    # 4. Create piper-client.py
    client_script_path = os.path.join(BASE_DIR, "piper-client.py")
    log(f"Writing {client_script_path}...")
    with open(client_script_path, "w", encoding="utf-8") as f:
        f.write('''#!/usr/bin/env python3
"""Piper TTS client — sends text to the piper server, outputs raw PCM to stdout."""

import os
import socket
import sys

SOCKET_PATH = os.path.expanduser("~/.cache/piper-server.sock")

def main() -> None:
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
    text = text.strip()
    if not text:
        return

    if not os.path.exists(SOCKET_PATH):
        print("piper-server not running", file=sys.stderr)
        sys.exit(1)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_PATH)
    sock.sendall(text.encode("utf-8"))
    sock.shutdown(socket.SHUT_WR)

    while True:
        data = sock.recv(65536)
        if not data:
            break
        sys.stdout.buffer.write(data)

    sock.close()

if __name__ == "__main__":
    main()
''')
    os.chmod(client_script_path, 0o755)

    # 5. Config speech-dispatcher modules
    sd_module_conf = os.path.join(MODULES_DIR, "piper-generic.conf")
    log(f"Writing {sd_module_conf}...")
    with open(sd_module_conf, "w", encoding="utf-8") as f:
        f.write(f'''# Piper TTS generic module for Speech Dispatcher
# Uses a persistent piper server to avoid model reload per sentence.

Debug 0

GenericExecuteSynth \\
"export XDATA='$DATA'; echo \\"$XDATA\\" | sed -z 's/\\\\n/ /g' | python3 {client_script_path} | paplay --raw --rate=22050 --channels=1 --format=s16le"

GenericCmdDependency "python3"
GenericSoundIconFolder "/usr/share/sounds/sound-icons/"

GenericPunctNone "0"
GenericPunctSome "0"
GenericPunctMost "0"
GenericPunctAll "0"
GenericStripPunctChars "@#$%^&*{{}}|\\\\"

GenericLanguage "en" "en" "utf-8"
GenericLanguage "en-us" "en-us" "utf-8"
GenericLanguage "en-gb" "en-gb" "utf-8"

AddVoice "en" "FEMALE1" "en_US-hfc_female-medium"
AddVoice "en-us" "FEMALE1" "en_US-hfc_female-medium"
''')

    # 6. Config speech-dispatcher global config
    sd_global_conf = os.path.join(CONFIG_DIR, "speechd.conf")
    log(f"Writing {sd_global_conf}...")
    with open(sd_global_conf, "w", encoding="utf-8") as f:
        f.write('''# User speech-dispatcher config
# Include system defaults first
Include "/etc/speech-dispatcher/speechd.conf"

# Add Piper module via sd_generic
AddModule "piper-generic" "sd_generic" "piper-generic.conf"

# Set Piper as the default TTS module
DefaultModule piper-generic

# Default language
DefaultLanguage "en"
''')

    # 7. Create and enable systemd user service
    service_path = os.path.join(SYSTEMD_DIR, "piper-server.service")
    log(f"Writing {service_path}...")
    with open(service_path, "w", encoding="utf-8") as f:
        f.write(f'''[Unit]
Description=Piper TTS Server (keeps model loaded for fast synthesis)
After=default.target

[Service]
Type=simple
ExecStart={venv_python} {server_script_path} {model_path}
Restart=on-failure
RestartSec=3
Environment=OMP_NUM_THREADS=8
Environment=ONNXRUNTIME_INTRA_OP_NUM_THREADS=8

[Install]
WantedBy=default.target
''')

    log("Enabling and starting systemd service...")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "piper-server.service"], check=True)
    subprocess.run(["systemctl", "--user", "restart", "piper-server.service"], check=True)

    log("Restarting speech-dispatcher...")
    subprocess.run(["killall", "-w", "speech-dispatcher"], capture_output=True)
    subprocess.run(["speech-dispatcher", "-d"], check=True)

    log("Testing configuration...")
    test_proc = subprocess.run(
        ["spd-say", "-w", "Setup completed successfully. Piper is now ready to speak."],
        capture_output=True,
    )
    if test_proc.returncode == 0:
        log("SUCCESS: Setup complete and speaking test succeeded!")
    else:
        log("WARNING: Setup complete, but test speech command returned error.")


if __name__ == "__main__":
    main()
