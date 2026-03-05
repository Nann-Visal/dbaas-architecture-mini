#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_from_directory
import os
import logging
import subprocess
import shutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

TENANTS_DIR = "/run/haproxy/tenants"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.makedirs(TENANTS_DIR, exist_ok=True)

def reload_haproxy():
    result = subprocess.run(
        ["sudo", "/bin/systemctl", "reload", "haproxy"],
        capture_output=True,
        text=True,
        timeout=15
    )
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Reload failed: {error_msg}")
    logger.info("HAProxy reloaded successfully via systemctl reload.")

def get_filename(port: int):
    return os.path.join(TENANTS_DIR, f"{port}.cfg")

def build_config_content(port: int, node_ip: str, db_port: int):
    return (
        f"listen node_{port}\n"
        f"    bind *:{port}\n"
        f"    mode tcp\n"
        f"    option tcplog\n"
        f"    server db1 {node_ip}:{db_port} check\n"
    )

def create_haproxy_file(port: int, node_ip: str, db_port: int):
    filename = get_filename(port)
    content = build_config_content(port, node_ip, db_port)
    backup = None

    if os.path.exists(filename):
        backup = filename + ".bak"
        shutil.copy(filename, backup)

    with open(filename, "w") as f:
        f.write(content)
    logger.info(f"Created HAProxy config: {filename} -> {node_ip}:{db_port}")

    try:
        reload_haproxy()
    except Exception as e:
        if backup:
            shutil.move(backup, filename)
        else:
            os.remove(filename)
        logger.error(f"HAProxy reload failed after create, rolled back: {e}")
        raise RuntimeError(f"HAProxy reload failed, rolled back: {e}")
    else:
        if backup:
            os.remove(backup)

    return filename

def delete_haproxy_file(port: int):
    filename = get_filename(port)
    if not os.path.exists(filename):
        return False

    backup = filename + ".bak"
    shutil.copy(filename, backup)
    os.remove(filename)
    logger.info(f"Deleted HAProxy config: {filename}")

    try:
        reload_haproxy()
    except Exception as e:
        shutil.move(backup, filename)
        logger.error(f"HAProxy reload failed after delete, rolled back: {e}")
        raise RuntimeError(f"HAProxy reload failed, rolled back deletion: {e}")
    else:
        os.remove(backup)

    return True

def ok(msg="success", data=None, code=200):
    body = {"status": "ok", "message": msg}
    if data is not None:
        body["data"] = data
    return jsonify(body), code

def err(msg, code=400):
    return jsonify({"status": "error", "message": msg}), code

# ─── API ──────────────────────────────────────────────────────────────
@app.route("/docs", methods=["GET"])
def docs():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/haproxy/config", methods=["POST"])
def api_create_config():
    d = request.json or {}
    for f in ["port", "node_ip", "db_port"]:
        if f not in d:
            return err(f"Missing required field: {f}")
    port    = int(d["port"])
    node_ip = d["node_ip"]
    db_port = int(d["db_port"])
    try:
        create_haproxy_file(port, node_ip, db_port)
        return ok(msg=f"HAProxy config for port {port} created and reloaded (-> {node_ip}:{db_port})")
    except Exception as e:
        return err(str(e), code=500)

@app.route("/haproxy/config", methods=["DELETE"])
def api_delete_config():
    d = request.json or {}
    if "port" not in d:
        return err("Missing required field: port")
    port = int(d["port"])
    try:
        if delete_haproxy_file(port):
            return ok(msg=f"HAProxy config for port {port} deleted and reloaded")
        else:
            return err(f"No config found for port {port}", code=404)
    except Exception as e:
        return err(str(e), code=500)

@app.route("/haproxy/configs", methods=["GET"])
def list_configs():
    files = [f for f in os.listdir(TENANTS_DIR) if f.endswith(".cfg")]
    return ok(msg="success", data=files)

@app.route("/haproxy/reload", methods=["POST"])
def api_reload():
    """Manual reload endpoint for debugging"""
    try:
        reload_haproxy()
        return ok(msg="HAProxy reloaded successfully")
    except Exception as e:
        return err(str(e), code=500)

@app.route("/health", methods=["GET"])
def health():
    return ok(msg="HAProxy config API is healthy")

if __name__ == "__main__":
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8080"))
    app.run(host=API_HOST, port=API_PORT, debug=False)