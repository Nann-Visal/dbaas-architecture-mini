# MySQL InnoDB Cluster Setup Guide

A step-by-step guide for deploying a production-grade MySQL InnoDB Cluster with MySQL Router and HAProxy for high availability and automatic failover.

---

## Prerequisites

> Use the **same MySQL Server version**, **same MySQL Shell version**, and preferably the **same OS family** on all nodes.
> Production deployment guidance for InnoDB Cluster starts with checking instance compatibility and configuration consistency across nodes.

---

## Step 1 — Prepare DNS or Hosts File on All DB Nodes

Add all cluster node IPs and hostnames to `/etc/hosts` so nodes can resolve each other by name.

```bash
sudo tee -a /etc/hosts >/dev/null <<'EOF'
10.10.10.1 db1
10.10.10.2 db2
10.10.10.3 db3
10.10.10.n dbn
EOF
```

---

## Step 2 — Install Packages on All DB Nodes

Install MySQL Server, MySQL Shell, and MySQL Router on every node in the cluster.

```bash
sudo apt update
sudo apt install -y mysql-server mysql-shell mysql-router
```

---

## Step 3 — Set MySQL Root Password and Ensure MySQL Is Reachable on All Nodes

Create a remote-accessible root user so MySQL Shell can connect to all nodes during cluster configuration.

```sql
mysql -uroot -p

CREATE USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY 'RootPass#2026';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
SELECT user, host, plugin FROM mysql.user WHERE user='root';
```

---

## Step 4 — Set Minimal MySQL Config on All DB Nodes

Apply a minimal cluster configuration to ensure MySQL listens on all interfaces and correctly reports its hostname to the cluster.

> ⚠️ Replace `db-host` with the actual hostname of each node (e.g. `db1`, `db2`, `db3`).

```bash
sudo tee /etc/mysql/mysql.conf.d/99-cluster.cnf >/dev/null <<'EOF'
[mysqld]
bind-address = 0.0.0.0
report_host = db-host
mysqlx-bind-address = 0.0.0.0
EOF

sudo systemctl restart mysql
sudo systemctl enable mysql
```

---

## Step 5 — Configure All MySQL Instances for InnoDB Cluster

Run this from any node or proxy that has network access to all DB nodes. This script uses MySQL Shell to prepare each instance for cluster membership by setting required configuration and creating a dedicated cluster admin user.

Create `configure-cluster.py`:

```bash
sudo tee configure-cluster.py >/dev/null <<'EOF'
rootPass = "RootPass#2026"
clusterAdmin = "clusteradmin"
clusterAdminPass = "ClusterAdmin#2026"

dba.configure_instance("root@10.10.10.1:3306", {
    "password": rootPass,
    "clusterAdmin": clusterAdmin,
    "clusterAdminPassword": clusterAdminPass,
    "restart": True
})

dba.configure_instance("root@10.10.10.2:3306", {
    "password": rootPass,
    "clusterAdmin": clusterAdmin,
    "clusterAdminPassword": clusterAdminPass,
    "restart": True
})

dba.configure_instance("root@10.10.10.3:3306", {
    "password": rootPass,
    "clusterAdmin": clusterAdmin,
    "clusterAdminPassword": clusterAdminPass,
    "restart": True
})

dba.configure_instance("root@10.10.10.n:3306", {
    "password": rootPass,
    "clusterAdmin": clusterAdmin,
    "clusterAdminPassword": clusterAdminPass,
    "restart": True
})

EOF

mysqlsh --py --file configure-cluster.py
```

---

## Step 6 — Create the Cluster and Add Standby Nodes

Connect to the first node (which becomes the initial primary), create the cluster, then add all remaining nodes using `clone` as the recovery method for automatic data synchronization.

Create `create-cluster.py`:

```bash
sudo tee create-cluster.py >/dev/null <<'EOF'
clusterAdmin = "clusteradmin"
clusterAdminPass = "ClusterAdmin#2026"

# Connect to first node (initial primary)
shell.connect(f"{clusterAdmin}@10.10.10.1:3306", clusterAdminPass)

# Create cluster
cluster = dba.create_cluster("nameOfCluster", {
    "multiPrimary": False
})

# Add second node
cluster.add_instance("clusteradmin@10.10.10.2:3306", {
    "password": clusterAdminPass,
    "recoveryMethod": "clone"
})

# Add third node
cluster.add_instance("clusteradmin@10.10.10.3:3306", {
    "password": clusterAdminPass,
    "recoveryMethod": "clone"
})

# Add n node
cluster.add_instance("clusteradmin@10.10.10.n:3306", {
    "password": clusterAdminPass,
    "recoveryMethod": "clone"
})

# Print cluster status
import json
print(json.dumps(cluster.status(), indent=2))

EOF

mysqlsh --py --file create-cluster.py
```

---

## Step 7 — Bootstrap MySQL Router on Each MySQL Node

MySQL Router acts as a middleware proxy, automatically routing read/write traffic to the correct cluster node. Bootstrap it on each DB node pointing to any active cluster member.

```bash
sudo mkdir -p /etc/mysqlrouter
sudo chown root:root /etc/mysqlrouter
sudo chmod 755 /etc/mysqlrouter

id mysqlrouter || sudo useradd -r -s /usr/sbin/nologin mysqlrouter

sudo mysqlrouter --bootstrap clusteradmin@10.10.10.n:3306 \
  --conf-use-gr-notifications \
  --conf-base-port 6446 \
  --directory /etc/mysqlrouter/nameOfCluster \
  --user=mysqlrouter
```

> **Default Router Ports after bootstrap:**
>
> | Port | Purpose |
> |------|---------|
> | 6446 | Read/Write (primary) |
> | 6447 | Read-only (secondaries) |
> | 6448 | Read/Write (classic protocol) |
> | 6449 | Read-only (classic protocol) |

---

## Step 8 — Create a systemd Service for Router on Each DB Node

Register MySQL Router as a systemd service so it starts automatically on boot and restarts on failure.

```bash
sudo tee /etc/systemd/system/mysqlrouter-prod.service >/dev/null <<'EOF'
[Unit]
Description=MySQL Router for nameOfCluster
After=network.target mysql.service
Wants=network.target

[Service]
Type=simple
User=mysqlrouter
Group=mysqlrouter
ExecStart=/usr/bin/mysqlrouter -c /etc/mysqlrouter/nameOfCluster/mysqlrouter.conf
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mysqlrouter-prod
sudo systemctl restart mysqlrouter-prod
sudo systemctl status mysqlrouter-prod
```

---

## Step 9 — Configure HAProxy to Point to Router Ports

On the HAProxy node, create a configuration block per tenant/port under `/var/lib/proxy-api/tenants/{port}.cfg`. HAProxy load-balances incoming connections across all Router instances using `leastconn` and performs TCP health checks.

```bash
listen mysql_{port}
    mode tcp
    balance leastconn
    option tcp-check
    server db1 10.10.10.1:6447 check inter 2s fall 3 rise 2
    server db2 10.10.10.2:6447 check inter 2s fall 3 rise 2
    server db3 10.10.10.3:6447 check inter 2s fall 3 rise 2
    server dbn 10.10.10.n:6447 check inter 2s fall 3 rise 2

sudo haproxy -c -f /var/lib/proxy-api/tenants/{port}.cfg
sudo systemctl enable haproxy
sudo systemctl restart haproxy
sudo systemctl status haproxy
```

> **Note:** Port `6447` is the read-only Router port. Use `6446` if you need to route read/write traffic through HAProxy instead.

---

## Step 10 — Status Check Script

Use this script to query the live cluster status at any time via MySQL Shell. The output will show the role of each node (`PRIMARY` / `SECONDARY`), their online status, and replication health.

```bash
#!/usr/bin/env bash
set -euo pipefail

mysqlsh --py -u clusteradmin -h 10.10.189.18 -P 3306 -p -e \
"import json; print(json.dumps(dba.get_cluster('prodCluster').status(), indent=2))"

chmod +x cluster-status.sh
./cluster-status.sh
```

---

## Architecture Overview

```
                        ┌─────────────┐
      App Clients ──▶   │   HAProxy   │  (TCP Load Balancer)
                        └──────┬──────┘
                               │ port 6446/6447
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │MySQL Rtr │    │MySQL Rtr │    │MySQL Rtr │  (on each DB node)
        └────┬─────┘    └────┬─────┘    └────┬─────┘
             │               │               │
        ┌────▼─────┐    ┌────▼─────┐    ┌────▼─────┐
        │  db1     │    │  db2     │    │  db3     │
        │ PRIMARY  │◀──▶│SECONDARY │◀──▶│SECONDARY │  InnoDB Cluster
        └──────────┘    └──────────┘    └──────────┘
```