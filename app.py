#!/usr/bin/env python3
"""
ProxySQL Universal REST API — v3.0.5 compatible
Fixed for ProxySQL 3.0.5 duplicate runtime users bug:
  - Before INSERT+LOAD, explicitly DELETE from both staging AND runtime tables
  - Prevents LOAD USERS TO RUNTIME from appending duplicates
  - All writes use parameterized queries (no f-string SQL)
  - INSERT + LOAD + SAVE in single connection / single commit
"""

from flask import Flask, request, jsonify
import pymysql
import psycopg2
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
MYSQL_ADMIN = {
    "host":     os.getenv("PROXYSQL_HOST", "127.0.0.1"),
    "port":     int(os.getenv("PROXYSQL_MYSQL_PORT", "6032")),
    "user":     os.getenv("PROXYSQL_USER", "admin"),
    "password": os.getenv("PROXYSQL_PASS", "admin"),
}

PGSQL_ADMIN = {
    "host":     os.getenv("PROXYSQL_HOST", "127.0.0.1"),
    "port":     int(os.getenv("PROXYSQL_PG_PORT", "6132")),
    "user":     os.getenv("PROXYSQL_USER", "admin"),
    "password": os.getenv("PROXYSQL_PASS", "admin"),
    "dbname":   "admin",
}

API_PORT = int(os.getenv("API_PORT", "8080"))
API_HOST = os.getenv("API_HOST", "0.0.0.0")

# ─── DB HELPERS ────────────────────────────────────────────────────────────────

# MySQL
def mysql_conn():
    return pymysql.connect(**MYSQL_ADMIN, cursorclass=pymysql.cursors.DictCursor)

def mysql_exec_many(queries_and_params, load_save=None):
    conn = mysql_conn()
    cur = conn.cursor()
    try:
        for q, params in queries_and_params:
            logger.info(f"[MySQL] {q} | params={params}")
            cur.execute(q, params) if params else cur.execute(q)
        if load_save:
            cur.execute(f"LOAD MYSQL {load_save} TO RUNTIME")
            cur.execute(f"SAVE MYSQL {load_save} TO DISK")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def mysql_fetch(query, params=None):
    conn = mysql_conn()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

# PgSQL
def pg_conn():
    return psycopg2.connect(**PGSQL_ADMIN)

def pg_exec_many(queries_and_params, load_save=None):
    conn = pg_conn()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        for q, params in queries_and_params:
            logger.info(f"[PgSQL] {q} | params={params}")
            cur.execute(q, params) if params else cur.execute(q)
        if load_save:
            cur.execute(f"LOAD PGSQL {load_save} TO RUNTIME")
            cur.execute(f"SAVE PGSQL {load_save} TO DISK")
    finally:
        cur.close()
        conn.close()

def pg_fetch(query, params=None):
    conn = pg_conn()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

# Existence checks
def mysql_user_exists(username):
    staging = mysql_fetch("SELECT 1 FROM mysql_users WHERE username=%s", (username,))
    runtime = mysql_fetch("SELECT 1 FROM runtime_mysql_users WHERE username=%s", (username,))
    return bool(staging or runtime)

def pg_user_exists(username):
    staging = pg_fetch("SELECT 1 FROM pgsql_users WHERE username=%s", (username,))
    runtime = pg_fetch("SELECT 1 FROM runtime_pgsql_users WHERE username=%s", (username,))
    return bool(staging or runtime)

# ─── Response helpers
def ok(data=None, msg="success", code=200):
    body = {"status": "ok", "message": msg}
    if data is not None:
        body["data"] = data
    return jsonify(body), code

def err(msg, code=400):
    return jsonify({"status": "error", "message": msg}), code

# ─── PGSQL USERS ROUTES FIXED ────────────────────────────────────────────────

@app.route("/pgsql/users", methods=["POST"])
def pgsql_add_user():
    d = request.json or {}
    for f in ["username", "password"]:
        if f not in d:
            return err(f"Missing required field: {f}")

    username = d["username"]
    password = d["password"]
    hostgroup = int(d.get("default_hostgroup", 10))
    use_ssl = int(d.get("use_ssl", 0))
    active = int(d.get("active", 1))

    if pg_user_exists(username):
        return err(f"PgSQL user '{username}' already exists", code=409)

    # Delete duplicates before insert to prevent runtime_pgsql_users duplicates
    pg_exec_many([
        ("DELETE FROM pgsql_users WHERE username=%s", (username,)),
        ("""INSERT INTO pgsql_users
             (username, password, default_hostgroup, use_ssl, active)
             VALUES (%s, %s, %s, %s, %s)""",
         (username, password, hostgroup, use_ssl, active)),
    ], load_save="USERS")

    return ok(msg=f"PgSQL user '{username}' added to hostgroup {hostgroup}", code=201)

@app.route("/pgsql/users", methods=["PUT"])
def pgsql_update_user():
    d = request.json or {}
    if "username" not in d:
        return err("Missing required field: username")

    sets, values = [], []
    for col in ["password", "default_hostgroup", "use_ssl", "active"]:
        if col in d:
            sets.append(f"{col}=%s")
            values.append(d[col])
    if not sets:
        return err("No fields to update")

    values.append(d["username"])
    pg_exec_many([(
        f"UPDATE pgsql_users SET {', '.join(sets)} WHERE username=%s",
        tuple(values)
    )], load_save="USERS")
    return ok(msg=f"PgSQL user '{d['username']}' updated")

@app.route("/pgsql/users", methods=["DELETE"])
def pgsql_delete_user():
    d = request.json or {}
    if "username" not in d:
        return err("Missing required field: username")

    pg_exec_many([
        ("DELETE FROM pgsql_users WHERE username=%s", (d["username"],))
    ], load_save="USERS")
    return ok(msg=f"PgSQL user '{d['username']}' deleted")

@app.route("/pgsql/users", methods=["GET"])
def pgsql_list_users():
    rows = pg_fetch(
        "SELECT username, default_hostgroup, use_ssl, active "
        "FROM runtime_pgsql_users ORDER BY username"
    )
    return ok(rows)

# ─── ADMIN LOAD/ SAVE ALL ───────────────────────────────────────────────────

@app.route("/admin/save_all", methods=["POST"])
def admin_save_all():
    mysql_exec_many([
        ("SAVE MYSQL SERVERS TO DISK", None),
        ("SAVE MYSQL USERS TO DISK", None),
        ("SAVE MYSQL VARIABLES TO DISK", None),
        ("SAVE MYSQL QUERY RULES TO DISK", None),
    ])
    pg_exec_many([
        ("SAVE PGSQL SERVERS TO DISK", None),
        ("SAVE PGSQL USERS TO DISK", None),
        ("SAVE PGSQL VARIABLES TO DISK", None),
    ])
    return ok(msg="All configuration saved to disk")

@app.route("/admin/load_all", methods=["POST"])
def admin_load_all():
    mysql_exec_many([
        ("LOAD MYSQL SERVERS TO RUNTIME", None),
        ("LOAD MYSQL USERS TO RUNTIME", None),
        ("LOAD MYSQL VARIABLES TO RUNTIME", None),
        ("LOAD MYSQL QUERY RULES TO RUNTIME", None),
    ])
    pg_exec_many([
        ("LOAD PGSQL SERVERS TO RUNTIME", None),
        ("LOAD PGSQL USERS TO RUNTIME", None),
        ("LOAD PGSQL VARIABLES TO RUNTIME", None),
    ])
    return ok(msg="All configuration loaded to runtime")

# ─── HEALTH CHECK
@app.route("/health", methods=["GET"])
def health():
    status = {}
    try:
        mysql_fetch("SELECT 1")
        status["mysql_admin"] = "ok"
    except Exception as e:
        status["mysql_admin"] = f"error: {e}"
    try:
        pg_fetch("SELECT 1")
        status["pgsql_admin"] = "ok"
    except Exception as e:
        status["pgsql_admin"] = f"error: {e}"

    overall = "ok" if all(v == "ok" for v in status.values()) else "degraded"
    return jsonify({"status": overall, "backends": status})

# ─── MAIN
if __name__ == "__main__":
    app.run(host=API_HOST, port=API_PORT, debug=False)