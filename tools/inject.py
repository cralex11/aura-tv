#!/usr/bin/env python3
"""Aura TV - Home Screen Injector for Smart TVs (VIDAA OS / RemoteNow)

Injects Aura TV as a permanent, first-class native tile onto your Smart TV home screen
via the local network MQTT protocol (port 36669). No developer mode or rooting required.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import ssl
import sys
import tempfile
import time
import urllib.parse
import uuid
import zlib

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: 'paho-mqtt' is required. Run: pip install paho-mqtt", file=sys.stderr)
    sys.exit(1)

MQTT_PORT = 36669
DEFAULT_APP_ID = "auratv"
DEFAULT_TITLE = "Aura TV"
DEFAULT_URL = "https://cralex11.github.io/aura-tv/"
DEFAULT_ICON = "https://raw.githubusercontent.com/cralex11/aura-tv/main/icon.png"

# Protocol constants
_K = b"v1tile"
def _deco(d, k): return bytes(b ^ k[i % len(k)] for i, b in enumerate(base64.b85decode(d)))
PATTERN = _deco("MF}upSs^t7L@!uSM*&SJUsF$TOkXM{GYLXpEnP!%", _K).decode("ascii")
VALUE_SUFFIX = _deco("9uOTVA4XC~Q2;UlP*7e7", _K).decode("ascii")
XOR_MASK = int.from_bytes(_deco("AgN#;M`qty", _K), "big")
OPERATION = "vidaacommon_001"

def _md5u(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_bundle_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "tv-client.bundle")

def load_client_cert_key() -> tuple[bytes, bytes]:
    path = get_bundle_path()
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Missing certificate bundle at {path}")
    with open(path, "rb") as f:
        blob = f.read()
    data = zlib.decompress(bytes(b ^ b"k3"[i % 2] for i, b in enumerate(base64.b85decode(blob))))
    marker = b"-----END CERTIFICATE-----"
    idx = data.find(marker) + len(marker)
    return data[:idx] + b"\n", data[idx:].strip() + b"\n"

def get_tv_timestamp(host: str) -> int:
    import http.client, email.utils
    for port in (18400, 38400, 80):
        try:
            conn = http.client.HTTPConnection(host, port, timeout=2)
            conn.request("GET", "/MediaServer/rendererdevicedesc.xml")
            r = conn.getresponse()
            r.read()
            date = r.headers.get("Date", "")
            if date:
                dt = email.utils.parsedate_to_datetime(date)
                return int(dt.timestamp())
        except Exception:
            pass
        finally:
            try: conn.close()
            except Exception: pass
    return int(time.time())

def generate_credentials(device_uuid: str, timestamp: int, token: str | None = None) -> tuple[str, str, str]:
    clean = device_uuid.replace("-", ":").lower()
    race = _md5u(f"{PATTERN}${clean}")[:6]
    client_id = f"{clean}$his${race}_{OPERATION}"
    username = f"his${timestamp ^ XOR_MASK}"
    if token:
        return client_id, username, token
    digit = sum(int(d) for d in str(timestamp)) % 10
    salt = VALUE_SUFFIX
    val_md5 = _md5u(f"his{digit}{salt}")[:6]
    password = _md5u(f"{timestamp}${val_md5}")
    return client_id, username, password

class TVConnection:
    def __init__(self, host: str, device_uuid: str, timestamp: int, token: str | None = None):
        self.host = host
        self.device_uuid = device_uuid
        self.client_id, self.username, self.password = generate_credentials(device_uuid, timestamp, token)
        self.messages: list[tuple[str, str]] = []
        self.connected = False
        
        self.client = mqtt.Client(client_id=self.client_id, protocol=mqtt.MQTTv311)
        cert, key = load_client_cert_key()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with tempfile.TemporaryDirectory(prefix="aura-tls-") as td:
            cp, kp = os.path.join(td, "c.pem"), os.path.join(td, "k.pem")
            with open(cp, "wb") as f: f.write(cert)
            with open(kp, "wb") as f: f.write(key)
            ctx.load_cert_chain(cp, kp)
            
        self.client.tls_set_context(ctx)
        self.client.tls_insecure_set(True)
        self.client.username_pw_set(self.username, self.password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, c, u, flags, rc, *a):
        val = getattr(rc, "value", rc)
        self.connected = (val == 0)

    def _on_message(self, c, u, msg):
        self.messages.append((msg.topic, msg.payload.decode("utf-8", "replace")))

    def start(self, timeout=6.0) -> bool:
        self.client.connect(self.host, MQTT_PORT, 30)
        self.client.loop_start()
        start = time.time()
        while time.time() - start < timeout:
            if self.connected:
                return True
            time.sleep(0.1)
        return False

    def stop(self):
        try: self.client.disconnect()
        except Exception: pass
        finally: self.client.loop_stop()

    def publish(self, topic: str, payload: str = ""):
        self.client.publish(topic, payload)

    def wait_for(self, suffix: str, timeout: float = 10.0, since: int = 0) -> str | None:
        end = time.time() + timeout
        while time.time() < end:
            for t, p in self.messages[since:]:
                if t.endswith(suffix):
                    return p
            time.sleep(0.2)
        return None

def get_session_file() -> str:
    path = os.path.expanduser("~/.aura_tv/session.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

def pair_tv(host: str) -> dict:
    device_uuid = ":".join(f"{b:02x}" for b in uuid.uuid4().bytes[:6])
    ts = get_tv_timestamp(host)
    print(f"Connecting to TV at {host}:{MQTT_PORT}...")
    conn = TVConnection(host, device_uuid, ts)
    if not conn.start():
        raise ConnectionError("Failed to connect over MQTT TLS to TV. Check TV IP and network connection.")

    mob_prefix = f"/remoteapp/mobile/{conn.client_id}/"
    ui_prefix = f"/remoteapp/tv/ui_service/{conn.client_id}/"
    plat_prefix = f"/remoteapp/tv/platform_service/{conn.client_id}/"

    conn.client.subscribe([
        (mob_prefix + "ui_service/data/authentication", 0),
        (mob_prefix + "ui_service/data/authenticationcode", 0),
        (mob_prefix + "platform_service/data/tokenissuance", 0),
    ])
    time.sleep(0.3)

    print("Requesting 4-digit pairing PIN on TV screen...")
    conn.publish(ui_prefix + "actions/vidaa_app_connect", json.dumps({
        "app_version": 2, "connect_result": 0, "device_type": "Mobile App"
    }))

    notif = conn.wait_for("data/authentication", timeout=15)
    if notif is None:
        conn.stop()
        raise TimeoutError("TV did not display the PIN dialog. If an old dialog is showing, dismiss it with the TV remote first.")

    pin = input("\nEnter the 4-digit PIN displayed on your TV screen: ").strip()
    since_pin = len(conn.messages)
    conn.publish(ui_prefix + "actions/authenticationcode", json.dumps({"authNum": int(pin)}))

    reply = conn.wait_for("ui_service/data/authenticationcode", timeout=12, since=since_pin)
    if not reply or json.loads(reply).get("result") != 1:
        conn.stop()
        raise ValueError("Invalid or expired PIN. Please try again.")

    print("PIN confirmed! Requesting permanent authorization token...")
    conn.publish(plat_prefix + "data/gettoken", json.dumps({"refreshtoken": ""}))
    conn.publish(ui_prefix + "actions/authenticationcodeclose", "")

    raw_token = conn.wait_for("platform_service/data/tokenissuance", timeout=15, since=since_pin)
    conn.stop()

    if not raw_token:
        raise TimeoutError("TV accepted PIN but did not issue an authorization token.")

    token_data = json.loads(raw_token)
    session = {
        "host": host,
        "device_uuid": device_uuid,
        "client_id": conn.client_id,
        "access_token": token_data.get("accesstoken"),
        "refresh_token": token_data.get("refreshtoken"),
    }
    with open(get_session_file(), "w") as f:
        json.dump(session, f, indent=2)
    print("Pairing successful! Credentials saved to ~/.aura_tv/session.json")
    return session

def inject_tile(host: str, app_id: str, title: str, url: str, icon_url: str):
    session_file = get_session_file()
    sidee_session = os.path.expanduser("~/.sidee/session.json")
    
    session = None
    if os.path.isfile(session_file):
        with open(session_file) as f: session = json.load(f)
    elif os.path.isfile(sidee_session):
        with open(sidee_session) as f: session = json.load(f)

    if not session or session.get("host") != host:
        session = pair_tv(host)

    ts = get_tv_timestamp(host)
    print(f"\nInjecting '{title}' ({url}) into TV launcher database...")
    conn = TVConnection(host, session["device_uuid"], ts, token=session.get("access_token"))
    if not conn.start():
        print("Existing token rejected. Re-pairing...")
        session = pair_tv(host)
        conn = TVConnection(host, session["device_uuid"], ts, token=session.get("access_token"))
        if not conn.start():
            raise ConnectionError("Could not authenticate with TV.")

    ui_topic = f"/remoteapp/tv/ui_service/{conn.client_id}/actions/uievent"
    payload = json.dumps({
        "type": "app_install",
        "app_info": {
            "Title": title,
            "StoreType": 99,
            "mediaId": app_id,
            "Id": app_id,
            "Image": icon_url,
            "URL": url,
            "configUrlDownload": 0,
            "configUrl": "",
        }
    })

    conn.publish(ui_topic, payload)
    print("Sent installation payload. Waiting 6 seconds for TV launcher database commit...")
    time.sleep(6)

    # Launch it immediately to confirm
    print(f"Sending launch signal for {title}...")
    launch_topic = f"/remoteapp/tv/ui_service/{conn.client_id}/actions/launchapp"
    conn.publish(launch_topic, json.dumps({
        "appId": app_id, "name": title, "url": url,
        "urlType": 37, "appName": title, "appUrl": url
    }))
    time.sleep(2)
    conn.stop()

    print("\n" + "=" * 60)
    print(f"SUCCESS: '{title}' is now permanently registered on your TV!")
    print("=" * 60)
    print("\nNext Steps to Pin as #1 on TV:")
    print("1. Press 'Home' on your TV remote.")
    print(f"2. Highlight '{title}' in your Apps row, hold OK for 2 seconds (or press Options ☰).")
    print("3. Move it to the very first spot on the left (#1).")
    print("4. Set TV Settings -> System -> Advanced -> Power On Mode -> 'Remember Last App'.")
    print("=" * 60)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("host", help="IP address of your Smart TV (e.g. 192.168.1.50)")
    p.add_argument("--url", default=DEFAULT_URL, help=f"Web URL to launch (default: {DEFAULT_URL})")
    p.add_argument("--title", default=DEFAULT_TITLE, help=f"Title in launcher (default: {DEFAULT_TITLE})")
    p.add_argument("--id", default=DEFAULT_APP_ID, help=f"App ID (default: {DEFAULT_APP_ID})")
    p.add_argument("--icon", default=DEFAULT_ICON, help=f"Icon image URL (default: {DEFAULT_ICON})")
    args = p.parse_args()

    inject_tile(args.host, args.id, args.title, args.url, args.icon)

if __name__ == "__main__":
    main()
