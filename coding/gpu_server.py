"""DigitalOcean GPU droplet manager for vLLM inference server.

CLI usage:
    uv run python gpu_server.py create    # First-time: base image + model download
    uv run python gpu_server.py snapshot  # Save droplet as snapshot for fast boots
    uv run python gpu_server.py start     # Boot from snapshot (daily use)
    uv run python gpu_server.py stop      # Destroy droplet
    uv run python gpu_server.py status    # Check droplet + vLLM health
    uv run python gpu_server.py wait      # Poll until vLLM is healthy
    uv run python gpu_server.py ssh       # SSH via Tailscale
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env from this directory and parent (for DO credentials)
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

CONFIG_PATH = Path(__file__).parent / "gpu_server_config.json"

# NOTE: The user_data templates below are for rebuilding from scratch if needed.
# The DO 1-click vLLM image has miniconda at /root/.miniconda3 with Python 3.12.
# vLLM and huggingface_hub are pip-installed into the conda base env.
# The model (Qwen3.5-35B-A3B-FP8) is cached in /root/.cache/huggingface.
# vLLM runs natively (not in Docker) via a systemd service.

USER_DATA_TEMPLATE = r"""#!/bin/bash
set -e

# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up --authkey={tailscale_authkey} --hostname={tailscale_hostname}

# Firewall: block all public inbound, allow only Tailscale + localhost
ufw default deny incoming
ufw default allow outgoing
ufw allow in on tailscale0
ufw allow in on lo
ufw --force enable

# Install vLLM and huggingface_hub into miniconda base env
source /root/.miniconda3/etc/profile.d/conda.sh
conda activate base
pip install -U vllm "huggingface_hub[cli]"

# Download FP8 model to HF cache
python -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3.5-35B-A3B-FP8')"

# Write vLLM systemd service
cat > /etc/systemd/system/vllm.service << 'EOF'
[Unit]
Description=vLLM Inference Server
After=network.target

[Service]
Type=simple
User=root
Restart=on-failure
RestartSec=10
ExecStart=/bin/bash -c 'source /root/.miniconda3/etc/profile.d/conda.sh && conda activate base && python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3.5-35B-A3B-FP8 --port 8000 --host 0.0.0.0 --max-model-len 131072 --tensor-parallel-size 1 --gpu-memory-utilization 0.95 --served-model-name qwen3.5-35b-a3b --no-enable-log-requests'
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vllm

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vllm
systemctl start vllm
"""

# Simpler user_data for snapshot boots — Tailscale reconnects automatically,
# ufw rules persist, vLLM service is already enabled.
SNAPSHOT_USER_DATA_TEMPLATE = r"""#!/bin/bash
set -e

# Re-auth Tailscale in case authkey expired
tailscale up --authkey={tailscale_authkey} --hostname={tailscale_hostname} --reset
"""


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def get_do_client():
    from pydo import Client

    token = os.environ.get("DO_API_TOKEN")
    if not token:
        print("Error: DO_API_TOKEN not set in .env")
        sys.exit(1)
    return Client(token=token)


def get_tailscale_authkey() -> str:
    key = os.environ.get("TAILSCALE_AUTHKEY")
    if not key:
        print("Error: TAILSCALE_AUTHKEY not set in .env")
        sys.exit(1)
    return key


# --- Status ---

def get_status() -> dict:
    """Check droplet and vLLM status. Safe to call from Flask."""
    config = load_config()
    result = {"droplet": "off", "vllm": "off", "droplet_id": None, "ip": None}

    if not config.get("droplet_id"):
        return result

    # Check droplet exists via DO API
    try:
        client = get_do_client()
        resp = client.droplets.get(droplet_id=config["droplet_id"])
        droplet = resp["droplet"]
        result["droplet"] = droplet["status"]  # "new", "active", "off"
        result["droplet_id"] = droplet["id"]
        # Get public IP
        for net in droplet.get("networks", {}).get("v4", []):
            if net["type"] == "public":
                result["ip"] = net["ip_address"]
                break
    except Exception:
        # Droplet no longer exists
        config["droplet_id"] = None
        save_config(config)
        return result

    # Check vLLM health via Tailscale
    result["vllm"] = check_vllm_health(config)
    return result


def check_vllm_health(config: dict) -> str:
    """Ping vLLM health endpoint. Returns 'ready', 'loading', or 'off'."""
    host = config.get("vllm_host", "dissertation-gpu")
    port = config.get("vllm_port", 8000)
    try:
        r = requests.get(f"http://{host}:{port}/health", timeout=5)
        return "ready" if r.ok else "loading"
    except requests.ConnectionError:
        return "off"
    except requests.Timeout:
        return "loading"
    except Exception:
        return "off"


# --- Droplet Lifecycle ---

def create_droplet(from_snapshot: bool = False) -> dict:
    """Create a GPU droplet. from_snapshot=True for daily use, False for first-time."""
    config = load_config()
    client = get_do_client()
    authkey = get_tailscale_authkey()

    if config.get("droplet_id"):
        print(f"Droplet already exists (id={config['droplet_id']}). Run 'stop' first.")
        sys.exit(1)

    if from_snapshot:
        if not config.get("snapshot_id"):
            print("No snapshot_id in config. Run 'create' first, then 'snapshot'.")
            sys.exit(1)
        image = config["snapshot_id"]
        user_data = SNAPSHOT_USER_DATA_TEMPLATE.format(tailscale_authkey=authkey, tailscale_hostname=config.get("vllm_host", "dissertation-gpu"))
        print(f"Creating droplet from snapshot {image}...")
    else:
        image = config["base_image"]
        user_data = USER_DATA_TEMPLATE.format(tailscale_authkey=authkey, tailscale_hostname=config.get("vllm_host", "dissertation-gpu"))
        print(f"Creating droplet from base image '{image}'...")

    body = {
        "name": config["droplet_name"],
        "region": config["region"],
        "size": config["size"],
        "image": image,
        "ssh_keys": config["ssh_keys"],
        "backups": False,
        "ipv6": False,
        "monitoring": True,
        "tags": config["tags"],
        "vpc_uuid": config["vpc_uuid"],
        "user_data": user_data,
    }

    resp = client.droplets.create(body=body)
    droplet = resp["droplet"]
    droplet_id = droplet["id"]
    config["droplet_id"] = droplet_id
    save_config(config)
    print(f"Droplet created (id={droplet_id}). Waiting for it to become active...")

    # Poll until active
    for _ in range(60):  # 5 min max
        time.sleep(5)
        try:
            resp = client.droplets.get(droplet_id=droplet_id)
            status = resp["droplet"]["status"]
            if status == "active":
                ip = None
                for net in resp["droplet"].get("networks", {}).get("v4", []):
                    if net["type"] == "public":
                        ip = net["ip_address"]
                print(f"Droplet active! Public IP: {ip}")
                print(f"Tailscale hostname: {config['vllm_host']}")
                break
        except Exception as e:
            print(f"  Polling... ({e})")
    else:
        print("Timed out waiting for droplet to become active.")
        return get_status()

    # Create firewall on first create (not from snapshot)
    if not from_snapshot and not config.get("firewall_id"):
        _create_firewall(client, config, droplet_id)

    # Assign existing firewall to new droplet (snapshot boots)
    if from_snapshot and config.get("firewall_id"):
        try:
            client.firewalls.assign_droplets(
                firewall_id=config["firewall_id"],
                body={"droplet_ids": [droplet_id]},
            )
            print(f"Firewall {config['firewall_id']} assigned to droplet.")
        except Exception as e:
            print(f"Warning: Could not assign firewall: {e}")

    return get_status()


def _create_firewall(client, config: dict, droplet_id: int):
    """Create a DO Cloud Firewall that blocks all inbound on public interface."""
    try:
        resp = client.firewalls.create(body={
            "name": "dissertation-gpu-lockdown",
            "droplet_ids": [droplet_id],
            "inbound_rules": [],  # No inbound allowed
            "outbound_rules": [
                {
                    "protocol": "tcp",
                    "ports": "all",
                    "destinations": {"addresses": ["0.0.0.0/0", "::/0"]},
                },
                {
                    "protocol": "udp",
                    "ports": "all",
                    "destinations": {"addresses": ["0.0.0.0/0", "::/0"]},
                },
                {
                    "protocol": "icmp",
                    "destinations": {"addresses": ["0.0.0.0/0", "::/0"]},
                },
            ],
            "tags": config["tags"],
        })
        fw_id = resp["firewall"]["id"]
        config["firewall_id"] = fw_id
        save_config(config)
        print(f"Firewall created (id={fw_id}) — all inbound blocked on public interface.")
    except Exception as e:
        print(f"Warning: Could not create firewall: {e}")


def destroy_droplet() -> dict:
    """Destroy the running droplet."""
    config = load_config()
    client = get_do_client()

    if not config.get("droplet_id"):
        print("No droplet running.")
        return {"droplet": "off", "vllm": "off"}

    droplet_id = config["droplet_id"]
    print(f"Destroying droplet {droplet_id}...")
    client.droplets.destroy(droplet_id=droplet_id)
    config["droplet_id"] = None
    save_config(config)
    print("Droplet destroyed.")
    return {"droplet": "off", "vllm": "off"}


def create_snapshot() -> dict:
    """Take a snapshot of the running droplet."""
    config = load_config()
    client = get_do_client()

    if not config.get("droplet_id"):
        print("No droplet running. Nothing to snapshot.")
        sys.exit(1)

    droplet_id = config["droplet_id"]
    snap_name = f"vllm-qwen3.5-{datetime.now().strftime('%Y%m%d-%H%M')}"
    print(f"Creating snapshot '{snap_name}' of droplet {droplet_id}...")

    # Trigger snapshot action
    resp = client.droplet_actions.post(
        droplet_id=droplet_id,
        body={"type": "snapshot", "name": snap_name},
    )
    action_id = resp["action"]["id"]

    # Poll until complete
    print("Waiting for snapshot to complete (this may take several minutes)...")
    for i in range(360):  # 60 min max
        time.sleep(10)
        try:
            action = client.actions.get(action_id=action_id)
            status = action["action"]["status"]
            if status == "completed":
                print("Snapshot complete!")
                break
            elif status == "errored":
                print("Snapshot failed!")
                return {"error": "snapshot failed"}
            if i % 6 == 0:
                print(f"  Still snapshotting... ({i * 10}s)")
        except Exception as e:
            print(f"  Polling... ({e})")
    else:
        print("Timed out waiting for snapshot.")
        return {"error": "timeout"}

    # Find the snapshot ID
    snapshots = client.snapshots.list(resource_type="droplet")
    for snap in snapshots.get("snapshots", []):
        if snap["name"] == snap_name:
            config["snapshot_id"] = snap["id"]
            save_config(config)
            print(f"Snapshot saved: id={snap['id']}, name={snap_name}")
            return {"snapshot_id": snap["id"], "name": snap_name}

    print("Warning: Snapshot completed but could not find it in the list.")
    return {"error": "snapshot not found"}


def wait_for_vllm(timeout: int = 600):
    """Poll until vLLM health endpoint returns OK."""
    config = load_config()
    host = config.get("vllm_host", "dissertation-gpu")
    port = config.get("vllm_port", 8000)
    url = f"http://{host}:{port}/health"

    print(f"Waiting for vLLM at {url} (timeout={timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=5)
            if r.ok:
                elapsed = int(time.time() - start)
                print(f"vLLM is ready! ({elapsed}s)")
                return True
        except Exception:
            pass
        time.sleep(10)
        elapsed = int(time.time() - start)
        if elapsed % 60 < 10:
            print(f"  Still waiting... ({elapsed}s)")

    print("Timed out waiting for vLLM.")
    return False


# --- CLI ---

def print_status(status: dict):
    droplet = status.get("droplet", "off")
    vllm = status.get("vllm", "off")
    ip = status.get("ip")

    icons = {"off": "⊘", "new": "◔", "active": "●", "ready": "●", "loading": "◔"}
    colors = {"off": "\033[31m", "new": "\033[33m", "active": "\033[32m",
              "ready": "\033[32m", "loading": "\033[33m"}
    reset = "\033[0m"

    print(f"  Droplet: {colors.get(droplet, '')}{icons.get(droplet, '?')} {droplet}{reset}"
          + (f"  (id={status.get('droplet_id')})" if status.get('droplet_id') else ""))
    if ip:
        print(f"       IP: {ip}")
    print(f"     vLLM: {colors.get(vllm, '')}{icons.get(vllm, '?')} {vllm}{reset}")

    config = load_config()
    print(f"  Host: {config.get('vllm_host', 'dissertation-gpu')}:{config.get('vllm_port', 8000)}")
    if config.get("snapshot_id"):
        print(f"  Snapshot: {config['snapshot_id']}")


def main():
    parser = argparse.ArgumentParser(description="Manage GPU droplet for vLLM inference")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("create", help="Create droplet from base image (first time)")
    sub.add_parser("start", help="Create droplet from snapshot (daily use)")
    sub.add_parser("stop", help="Destroy running droplet")
    sub.add_parser("status", help="Show droplet and vLLM status")
    sub.add_parser("snapshot", help="Snapshot running droplet")
    sub.add_parser("ssh", help="SSH into droplet via Tailscale")
    wait_p = sub.add_parser("wait", help="Wait for vLLM to become healthy")
    wait_p.add_argument("--timeout", type=int, default=600, help="Timeout in seconds")

    args = parser.parse_args()

    if args.command == "create":
        create_droplet(from_snapshot=False)
    elif args.command == "start":
        create_droplet(from_snapshot=True)
    elif args.command == "stop":
        destroy_droplet()
    elif args.command == "status":
        status = get_status()
        print_status(status)
    elif args.command == "snapshot":
        create_snapshot()
    elif args.command == "ssh":
        config = load_config()
        host = config.get("vllm_host", "dissertation-gpu")
        os.execvp("ssh", ["ssh", f"root@{host}"])
    elif args.command == "wait":
        wait_for_vllm(timeout=args.timeout)


if __name__ == "__main__":
    main()
