# Piper TTS + Speech Dispatcher Installer

A single Python script that sets up [Piper TTS](https://github.com/rhasspy/piper) as your system's text-to-speech voice on Linux. No `sudo` needed.

It installs Piper, downloads the `hfc_female` English voice, runs a background server that keeps the voice loaded (so speech starts fast), and plugs it into Speech Dispatcher. Everything starts automatically at login.

## What it does

1. Creates a Python virtual environment and installs `piper-tts`.
2. Downloads the `en_US-hfc_female-medium` voice from Hugging Face.
3. Writes a small Piper **server** and **client** script.
4. Creates a Speech Dispatcher module config that uses the client.
5. Sets Piper as the default Speech Dispatcher voice.
6. Creates and starts a systemd **user** service for the server.
7. Restarts Speech Dispatcher and plays a test message.

## Requirements

- Linux with systemd (user services)
- Python 3 with the `venv` module
- Speech Dispatcher (`speech-dispatcher`, `spd-say`)
- PulseAudio or PipeWire with `paplay`
- `killall` (from the `psmisc` package)
- Internet access (for pip and the voice download)

## Usage

```bash
python3 install_piper.py
```

If setup works, you will hear: *"Setup completed successfully. Piper is now ready to speak."*

Try it any time:

```bash
spd-say "Hello from Piper"
```

## Where things go

| What | Location |
| --- | --- |
| Python venv | `~/.local/share/piper-venv` |
| Voice model, server and client scripts | `~/.local/share/piper-voices` |
| Speech Dispatcher config | `~/.config/speech-dispatcher/speechd.conf` |
| Piper module config | `~/.config/speech-dispatcher/modules/piper-generic.conf` |
| systemd service | `~/.config/systemd/user/piper-server.service` |
| Server socket | `~/.cache/piper-server.sock` |

## How it works

The server loads the voice once and listens on a Unix socket (only your user can access it). When Speech Dispatcher needs to speak, the client sends the text to the server. The server sends back raw audio, and `paplay` plays it. This avoids reloading the voice for every sentence.

## Useful commands

```bash
systemctl --user status piper-server.service    # check the server
systemctl --user restart piper-server.service   # restart it
journalctl --user -u piper-server.service       # view logs
```

## Customizing

- **Different voice:** change `VOICE_ONNX_URL` and `VOICE_JSON_URL` at the top of the script. Also update the voice name in the module config and `--rate` if the sample rate differs.
- **CPU threads:** the service sets 8 threads. Edit the `OMP_NUM_THREADS` and `ONNXRUNTIME_INTRA_OP_NUM_THREADS` lines to match your CPU.
- **Install paths:** change the path variables at the top of the script.

## Notes

- The script **overwrites** `~/.config/speech-dispatcher/speechd.conf`. Back it up first if you have custom settings.
- The script includes `/etc/speech-dispatcher/speechd.conf`, so the system config must exist.
- Running it again is safe. It reinstalls the venv and skips voice files that are already downloaded.

## Troubleshooting

- **No sound:** check that `paplay` works and the server is running.
- **"piper-server not running":** run `systemctl --user restart piper-server.service` and check the logs.
- **Test speech failed:** make sure Speech Dispatcher is installed and your audio server is running.

## Credits

- [Piper](https://github.com/rhasspy/piper) by the Rhasspy project
- Voices from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
