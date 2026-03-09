# MySQL InnoDB Cluster — 3 Node Setup Guide

> Step-by-Step Implementation Guide with Explanations

---

## Node Information

| Hostname | IP Address     | Role      | OS / MySQL            |
|----------|----------------|-----------|-----------------------|
| node1    | 192.168.1.11   | Primary   | Ubuntu 22 / MySQL 8.0 |
| node2    | 192.168.1.12   | Secondary | Ubuntu 22 / MySQL 8.0 |
| node3    | 192.168.1.13   | Secondary | Ubuntu 22 / MySQL 8.0 |

> **💡 WHY 3 NODES?**  
> 3 nodes give you Quorum = 2/3. If 1 node dies, the remaining 2 still have majority and can automatically elect a new primary without any manual intervention.

---

## STEP 1 — Install MySQL Server on ALL 3 Nodes

**Why:** MySQL 8.0 ships with Group Replication plugin and InnoDB Cluster support out of the box. No extra plugins needed.

```bash
# Run on node1, node2, node3
sudo apt update
sudo apt install -y mysql-server

# Verify MySQL version (must be 8.0+)
mysql --version

# Start and enable MySQL
sudo systemctl start mysql
sudo systemctl enable mysql
```

> **⚠️ IMPORTANT**  
> All 3 nodes MUST run the same MySQL version. Mixed versions can cause replication errors.

---

## STEP 2 — Configure /etc/hosts on ALL Nodes

**Why:** InnoDB Cluster uses hostnames internally for Group Replication. If nodes cannot resolve each other's names, the cluster will fail to form.

```bash
# Edit /etc/hosts on ALL 3 nodes
sudo nano /etc/hosts

# Add these lines:
192.168.1.11    node1
192.168.1.12    node2
192.168.1.13    node3

# Test connectivity from node1
ping node2
ping node3
```

---

## STEP 3 — Configure MySQL on ALL Nodes (my.cnf)

**Why each setting matters:**

| Setting                        | Why It Is Needed                                                                 |
|--------------------------------|----------------------------------------------------------------------------------|
| `server_id`                    | Unique ID per node. Required for replication to identify each node.              |
| `binlog_format=ROW`            | Row-based binary log. Required by Group Replication for consistent data sync.    |
| `gtid_mode=ON`                 | Global Transaction ID. Allows nodes to track which transactions have been applied.|
| `enforce_gtid_consistency`     | Prevents transactions that cannot be tracked by GTID, ensuring data consistency. |
| `log_slave_updates=ON`         | Makes secondary nodes also write received transactions to their binary log.      |
| `plugin-load=group_replication`| Loads the Group Replication plugin automatically at startup.                     |

```bash
# Edit /etc/mysql/mysql.conf.d/mysqld.cnf on EACH node
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf

# ---- node1: server_id = 1 ----
[mysqld]
server_id = 1                          # CHANGE to 2 for node2, 3 for node3
bind-address = 0.0.0.0
binlog_format = ROW
log_bin = mysql-bin
gtid_mode = ON
enforce_gtid_consistency = ON
log_slave_updates = ON
master_info_repository = TABLE
relay_log_info_repository = TABLE
transaction_write_set_extraction = XXHASH64
plugin-load-add = group_replication.so
group_replication_group_name = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
group_replication_start_on_boot = OFF
group_replication_local_address = 'node1:33061'   # Change per node
group_replication_group_seeds = 'node1:33061,node2:33061,node3:33061'
group_replication_bootstrap_group = OFF

# Restart MySQL after editing
sudo systemctl restart mysql
```

> **💡 GROUP NAME**  
> The `group_replication_group_name` must be the same UUID on ALL nodes.  
> Generate one with: `python3 -c "import uuid; print(uuid.uuid4())"`

---

## STEP 4 — Create Admin User on ALL Nodes

**Why:** The cluster needs a privileged user with replication permissions on all nodes. This user is used by MySQL Shell when setting up and managing the cluster.

```sql
-- Run on ALL 3 nodes
sudo mysql -u root

-- Create cluster admin user
CREATE USER 'clusteradmin'@'%' IDENTIFIED BY 'StrongPassword123!';

-- Grant all required permissions
GRANT ALL PRIVILEGES ON *.* TO 'clusteradmin'@'%' WITH GRANT OPTION;
GRANT REPLICATION SLAVE ON *.* TO 'clusteradmin'@'%';
GRANT REPLICATION CLIENT ON *.* TO 'clusteradmin'@'%';

FLUSH PRIVILEGES;
EXIT;
```

> **🔐 SECURITY TIP**  
> Use a strong password. In production, restrict the host pattern to your internal network (e.g., `'192.168.1.%'`).

---

## STEP 5 — Install MySQL Shell on node1

**Why:** MySQL Shell provides the `dba` object (Database Admin API) with commands like `dba.createCluster()`, `cluster.addInstance()`, and `cluster.rejoinInstance()`.

```bash
# Install MySQL Shell on node1
sudo apt install -y mysql-shell

# Verify installation
mysqlsh --version

# Connect to test
mysqlsh clusteradmin@node1:3306
```

---

## STEP 6 — Check Nodes are Ready for Cluster

**Why:** This step checks if binary logging, GTID mode, and all required settings are correct. It saves you from mysterious errors later.

```js
// Connect with MySQL Shell from node1
mysqlsh clusteradmin@node1:3306

// Check and auto-fix node1 configuration
dba.checkInstanceConfiguration('clusteradmin@node1:3306')

// If issues found, auto-fix them:
dba.configureInstance('clusteradmin@node1:3306')

// Repeat for node2 and node3
dba.checkInstanceConfiguration('clusteradmin@node2:3306')
dba.configureInstance('clusteradmin@node2:3306')

dba.checkInstanceConfiguration('clusteradmin@node3:3306')
dba.configureInstance('clusteradmin@node3:3306')

// Expected output: 'Instance is ready for InnoDB Cluster usage.'
```

> **⚠️ RESTART REQUIRED**  
> After `dba.configureInstance()`, MySQL Shell may ask you to restart MySQL on that node.  
> Run: `sudo systemctl restart mysql`

---

## STEP 7 — Create the InnoDB Cluster (node1)

**Why:** `dba.createCluster()` bootstraps Group Replication on node1, creates internal cluster metadata tables, and designates node1 as the initial primary.

```js
// From MySQL Shell on node1
mysqlsh clusteradmin@node1:3306

// Create the cluster
var cluster = dba.createCluster('MyCluster')

// Verify it was created
cluster.status()

// Expected output:
// {
//   'clusterName': 'MyCluster',
//   'defaultReplicaSet': {
//     'status': 'OK_NO_TOLERANCE',    <- OK but only 1 node so far
//     'topology': {
//       'node1:3306': { 'mode': 'R/W', 'status': 'ONLINE' }
//     }
//   }
// }
```

> **💡 STATUS: OK_NO_TOLERANCE**  
> This means the cluster is working but cannot tolerate any failure yet (only 1 node).  
> After adding nodes 2 and 3, status will become `OK`.

---

## STEP 8 — Add node2 and node3 to the Cluster

**Why:** `addInstance()` connects node2/node3 to the Group Replication group, synchronizes all existing data to them (using MySQL Clone internally), and registers them as cluster members.

```js
// Still in MySQL Shell on node1

// Add node2
cluster.addInstance('clusteradmin@node2:3306')

// MySQL Shell will ask how to sync data:
// Choose 'Clone' for fastest sync (recommended)
// OR choose 'Incremental' if data is small

// Wait for node2 to sync... then add node3
cluster.addInstance('clusteradmin@node3:3306')

// Check final status
cluster.status()

// Expected output — all 3 nodes ONLINE:
// 'status': 'OK'
// 'node1:3306': { 'mode': 'R/W', 'status': 'ONLINE' }
// 'node2:3306': { 'mode': 'R/O', 'status': 'ONLINE' }
// 'node3:3306': { 'mode': 'R/O', 'status': 'ONLINE' }
```

> **✅ STATUS: OK**  
> When all 3 nodes show ONLINE and status is `OK`, your cluster is fully operational!  
> It can now tolerate 1 node failure without any service interruption.

---

## STEP 9 — Install & Configure MySQL Router

**Why:** Without MySQL Router, if the primary changes (failover), your application would need to know the new primary IP. MySQL Router handles this transparently — your app always connects to the same Router address.

```bash
# Install MySQL Router (can be on node1 or a separate server)
sudo apt install -y mysql-router

# Bootstrap Router — connects it to the cluster metadata
mysqlrouter --bootstrap clusteradmin@node1:3306 --user=mysqlrouter

# Start MySQL Router
sudo systemctl start mysqlrouter
sudo systemctl enable mysqlrouter

# Router now listens on:
# Port 6446 -> PRIMARY (Read/Write)
# Port 6447 -> SECONDARY (Read only, load balanced)

# Application connects to Router, not directly to MySQL:
mysql -h 127.0.0.1 -P 6446 -u appuser -p    # writes -> primary
mysql -h 127.0.0.1 -P 6447 -u appuser -p    # reads  -> secondary
```

---

## STEP 10 — Enable Auto-Rejoin on ALL Nodes

**Why:** Without auto-rejoin, a node that crashes and recovers will sit offline until a DBA manually runs `rejoinInstance()`. With auto-rejoin, the node tries to reconnect automatically.

```sql
-- Connect to each node and run:
mysql -u clusteradmin -p -h node1

-- Auto-rejoin: try 3 times before giving up
SET PERSIST group_replication_autorejoin_tries = 3;

-- Wait 5 seconds between each retry
SET PERSIST group_replication_autorejoin_delay = 5;

-- Repeat on node2 and node3
-- SET PERSIST means setting survives MySQL restart
```

> **💡 SET PERSIST**  
> `SET PERSIST` saves the setting so it survives MySQL restarts. No need to edit `my.cnf` manually.

---

## Automatic Failover — How It Works

When node1 (primary) fails, here is exactly what happens:

| # | Time    | What Happens                                                                                      |
|---|---------|---------------------------------------------------------------------------------------------------|
| 1 | T+0 sec | node1 crashes. node2 and node3 stop receiving heartbeat from node1.                               |
| 2 | T+5 sec | node2 and node3 detect node1 is unreachable. They have 2/3 quorum, so they can act.              |
| 3 | T+10 sec| Group Replication elects a new primary (e.g., node2) using internal voting. No human needed.     |
| 4 | T+15 sec| node2 becomes PRIMARY (R/W). node3 remains SECONDARY (R/O). MySQL Router detects the change.     |
| 5 | T+20 sec| Application traffic is rerouted to node2. Brief pause during election (~5–30 sec).               |

### Manual Failover (planned maintenance)

```js
mysqlsh clusteradmin@node1:3306
var cluster = dba.getCluster()

// Switch primary to node2
cluster.setPrimaryInstance('clusteradmin@node2:3306')

// Verify
cluster.status()
```

---

## Rejoin — How It Works

When a node that was offline comes back, it needs to rejoin and catch up on missed transactions.

### Option A — Auto-Rejoin (if Step 10 was configured)

```bash
# Start MySQL on the recovered node
sudo systemctl start mysql

# Group Replication auto-rejoin kicks in:
# 1. node1 detects it was part of a cluster
# 2. node1 contacts current primary to get cluster state
# 3. node1 uses MySQL Clone to catch up on missed data
# 4. node1 rejoins as SECONDARY (read-only)

# Verify from MySQL Shell:
cluster.status()
# node1:3306 should show status: ONLINE, mode: R/O
```

### Option B — Manual Rejoin via MySQL Shell

```js
// Connect to current primary (node2)
mysqlsh clusteradmin@node2:3306

var cluster = dba.getCluster()

// Check status — node1 will show as MISSING or OFFLINE
cluster.status()

// Rejoin node1
cluster.rejoinInstance('clusteradmin@node1:3306')

// Verify
cluster.status()
// node1 should now be ONLINE
```

### Option C — Full Recovery (all nodes were down)

```js
// If ALL nodes crashed at the same time — cluster is frozen (no quorum)

// On the node with most recent data:
mysqlsh clusteradmin@node2:3306

// Force cluster back online
dba.rebootClusterFromCompleteOutage()

// Then rejoin other nodes
cluster.rejoinInstance('clusteradmin@node1:3306')
cluster.rejoinInstance('clusteradmin@node3:3306')
```

> **⚠️ USE rebootClusterFromCompleteOutage CAREFULLY**  
> Only run this if ALL nodes were down simultaneously.  
> Running it when the cluster is partially healthy can cause data inconsistency.  
> Always check `cluster.status()` first.

---

## Quick Reference Commands

| Task                          | Command (MySQL Shell)                              |
|-------------------------------|----------------------------------------------------|
| Check cluster status          | `cluster.status()`                                 |
| Get cluster object            | `var cluster = dba.getCluster()`                   |
| Add a new node                | `cluster.addInstance('admin@nodeX:3306')`          |
| Rejoin a node                 | `cluster.rejoinInstance('admin@nodeX:3306')`       |
| Remove a node                 | `cluster.removeInstance('admin@nodeX:3306')`       |
| Manual failover (planned)     | `cluster.setPrimaryInstance('admin@node2:3306')`   |
| Full recovery (all nodes down)| `dba.rebootClusterFromCompleteOutage()`            |
| Describe the cluster          | `cluster.describe()`                               |
| List all options              | `cluster.options()`                                |

## Port Reference

| Port  | Used By           | Purpose                              |
|-------|-------------------|--------------------------------------|
| 3306  | MySQL Server      | Standard MySQL client connections    |
| 33061 | Group Replication | Internal node-to-node communication  |
| 6446  | MySQL Router      | Read/Write (routes to PRIMARY)       |
| 6447  | MySQL Router      | Read Only (routes to SECONDARY)      |

---

> **✅ FINAL CHECK — Cluster is Healthy When:**
> 1. `cluster.status()` shows `OK`
> 2. All 3 nodes show `status: ONLINE`
> 3. node1 shows `mode: R/W` (Primary)
> 4. node2, node3 show `mode: R/O` (Secondary)
> 5. MySQL Router is running on ports 6446 / 6447