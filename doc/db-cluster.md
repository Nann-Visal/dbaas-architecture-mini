# MySQL InnoDB Cluster — Complete Production Setup Guide

> 3-Node High Availability with Full Failover, Auto-Rejoin, Monitoring & Split-Brain Protection

---

## Node Information

| Hostname | IP Address   | Role      | OS / MySQL            |
|----------|--------------|-----------|-----------------------|
| node1    | 192.168.1.11 | Primary   | Ubuntu 22 / MySQL 8.0 |
| node2    | 192.168.1.12 | Secondary | Ubuntu 22 / MySQL 8.0 |
| node3    | 192.168.1.13 | Secondary | Ubuntu 22 / MySQL 8.0 |

> **💡 WHY 3 NODES?**  
> Quorum = 2/3. If 1 node dies, the remaining 2 still have majority and can automatically elect a new primary without any manual intervention.

---

## STEP 1 — Install MySQL Server on ALL 3 Nodes

**Why:** MySQL 8.0 ships with Group Replication and InnoDB Cluster support built-in. No extra plugins needed.

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

**Why:** InnoDB Cluster uses hostnames internally. If nodes cannot resolve each other by name, the cluster will fail to form.

```bash
# Edit /etc/hosts on ALL 3 nodes
sudo nano /etc/hosts

# Add these lines:
192.168.1.11    node1
192.168.1.12    node2
192.168.1.13    node3

# Test connectivity
ping node2
ping node3
```

---

## STEP 3 — Configure MySQL on ALL Nodes (my.cnf)

**Why each setting matters:**

| Setting | Why It Is Needed |
|---|---|
| `server_id` | Unique ID per node. Required for replication. |
| `binlog_format=ROW` | Required by Group Replication for consistent data sync. |
| `gtid_mode=ON` | Allows nodes to track which transactions have been applied. |
| `enforce_gtid_consistency` | Prevents transactions that break GTID tracking. |
| `log_slave_updates=ON` | Secondary nodes also write received transactions to binary log. |
| `plugin-load=group_replication` | Loads Group Replication plugin at startup. |
| `group_replication_member_expel_timeout` | How long before a silent node is expelled. |
| `group_replication_autorejoin_tries` | How many times a node tries to rejoin automatically. |
| `group_replication_exit_state_action` | What a node does when it cannot stay in the cluster. |

```bash
# Edit /etc/mysql/mysql.conf.d/mysqld.cnf on EACH node
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf

[mysqld]
# ── Basic ──────────────────────────────────────────────────────
server_id = 1                            # CHANGE: 1=node1, 2=node2, 3=node3
bind-address = 0.0.0.0
binlog_format = ROW
log_bin = mysql-bin
gtid_mode = ON
enforce_gtid_consistency = ON
log_slave_updates = ON
master_info_repository = TABLE
relay_log_info_repository = TABLE
transaction_write_set_extraction = XXHASH64

# ── Group Replication ──────────────────────────────────────────
plugin-load-add = group_replication.so
group_replication_group_name = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'  # same on all nodes
group_replication_start_on_boot = OFF
group_replication_local_address = 'node1:33061'                         # CHANGE per node
group_replication_group_seeds = 'node1:33061,node2:33061,node3:33061'
group_replication_bootstrap_group = OFF
group_replication_single_primary_mode = ON
group_replication_enforce_update_everywhere_checks = OFF

# ── Failover Tuning ────────────────────────────────────────────
# How long (seconds) to wait before expelling an unresponsive node
group_replication_member_expel_timeout = 5

# How long to wait for majority if unreachable (0 = fail immediately)
group_replication_unreachable_majority_timeout = 10

# What this node does if it loses contact with the cluster
# READ_ONLY = safest (stays up but stops accepting writes)
# ABORT_SERVER = crashes MySQL (forces clean failover)
group_replication_exit_state_action = READ_ONLY

# ── Auto-Rejoin ────────────────────────────────────────────────
# How many times to retry rejoining after being expelled
group_replication_autorejoin_tries = 3

# Seconds to wait between each rejoin attempt
group_replication_autorejoin_delay = 60

# What to do while waiting to rejoin
# SUPER_READ_ONLY = node stays up but refuses writes (safest)
group_replication_recovery_get_public_key = ON

# ── Clone Plugin (for fast data sync on rejoin) ────────────────
plugin-load-add = mysql_clone.so

# Restart MySQL after editing
sudo systemctl restart mysql
```

> **💡 GROUP NAME**  
> Must be the same UUID on ALL nodes.  
> Generate: `python3 -c "import uuid; print(uuid.uuid4())"`

---

## STEP 4 — Create Admin User on ALL Nodes

**Why:** The cluster needs a privileged user with replication and backup permissions on all nodes.

```sql
-- Run on ALL 3 nodes
sudo mysql -u root

-- Create cluster admin user
CREATE USER 'clusteradmin'@'%' IDENTIFIED BY 'StrongPassword123!';

-- Core permissions
GRANT ALL PRIVILEGES ON *.* TO 'clusteradmin'@'%' WITH GRANT OPTION;
GRANT REPLICATION SLAVE ON *.* TO 'clusteradmin'@'%';
GRANT REPLICATION CLIENT ON *.* TO 'clusteradmin'@'%';

-- Required for Clone plugin (fast rejoin sync)
GRANT BACKUP_ADMIN ON *.* TO 'clusteradmin'@'%';

-- Required for cluster metadata
GRANT CLONE_ADMIN ON *.* TO 'clusteradmin'@'%';

FLUSH PRIVILEGES;
EXIT;
```

> **🔐 SECURITY TIP**  
> Restrict host to internal network in production: `'clusteradmin'@'192.168.1.%'`

---

## STEP 5 — Install & Enable Clone Plugin on ALL Nodes

**Why:** The Clone plugin allows a rejoining node to copy all missing data from an active node quickly — much faster than replaying binary logs. Without it, large databases take very long to resync.

```sql
-- Run on ALL 3 nodes
sudo mysql -u root

-- Install clone plugin
INSTALL PLUGIN clone SONAME 'mysql_clone.so';

-- Verify it is active
SELECT PLUGIN_NAME, PLUGIN_STATUS FROM information_schema.PLUGINS
WHERE PLUGIN_NAME = 'clone';
-- Expected: clone | ACTIVE

EXIT;
```

---

## STEP 6 — Install MySQL Shell on node1

**Why:** MySQL Shell provides the `dba` API to create and manage the cluster with commands like `dba.createCluster()`, `cluster.addInstance()`, `cluster.rejoinInstance()`.

```bash
# Install MySQL Shell on node1
sudo apt install -y mysql-shell

# Verify
mysqlsh --version
```

---

## STEP 7 — Check & Fix All Nodes (MySQL Shell)

**Why:** Verifies that binary logging, GTID, and all required settings are correct before creating the cluster. Prevents hard-to-debug errors later.

```js
// Connect from node1
mysqlsh clusteradmin@node1:3306

// Check and fix each node
dba.checkInstanceConfiguration('clusteradmin@node1:3306')
dba.configureInstance('clusteradmin@node1:3306')

dba.checkInstanceConfiguration('clusteradmin@node2:3306')
dba.configureInstance('clusteradmin@node2:3306')

dba.checkInstanceConfiguration('clusteradmin@node3:3306')
dba.configureInstance('clusteradmin@node3:3306')

// Expected: 'Instance is ready for InnoDB Cluster usage.'
```

> **⚠️ RESTART REQUIRED**  
> After `dba.configureInstance()`, restart MySQL on that node if prompted:  
> `sudo systemctl restart mysql`

---

## STEP 8 — Create the InnoDB Cluster (node1)

**Why:** Bootstraps Group Replication on node1, creates internal metadata, and designates node1 as the initial primary.

```js
// From MySQL Shell on node1
mysqlsh clusteradmin@node1:3306

var cluster = dba.createCluster('MyCluster', {
  // Auto-rejoin settings at cluster level
  autoRejoinTries: 3,

  // Expel unresponsive members after N seconds
  expelTimeout: 5,

  // What to do when node cannot stay in cluster
  exitStateAction: 'READ_ONLY',

  // Consistency level: EVENTUAL = fast, BEFORE_ON_PRIMARY_FAILOVER = safer
  consistency: 'BEFORE_ON_PRIMARY_FAILOVER',
})

cluster.status()
// Expected: status 'OK_NO_TOLERANCE' — cluster works but only 1 node
```

---

## STEP 9 — Add node2 and node3

**Why:** `addInstance()` joins nodes to Group Replication, syncs data via Clone, and registers them in cluster metadata.

```js
// Add node2
cluster.addInstance('clusteradmin@node2:3306', {
  recoveryMethod: 'clone',    // Use Clone plugin for fast sync
  autoRejoinTries: 3,
  exitStateAction: 'READ_ONLY',
})

// Add node3
cluster.addInstance('clusteradmin@node3:3306', {
  recoveryMethod: 'clone',
  autoRejoinTries: 3,
  exitStateAction: 'READ_ONLY',
})

// Verify all 3 nodes online
cluster.status()

// Expected:
// status: 'OK'
// node1:3306  mode: R/W  status: ONLINE   <- Primary
// node2:3306  mode: R/O  status: ONLINE   <- Secondary
// node3:3306  mode: R/O  status: ONLINE   <- Secondary
```

> **✅ STATUS: OK**  
> All 3 nodes ONLINE = cluster can tolerate 1 node failure automatically.

---

## STEP 10 — Install & Configure MySQL Router

**Why:** MySQL Router transparently routes your app to the correct node. When failover happens, your app does not need to change anything — Router handles it automatically.

```bash
# Install MySQL Router
sudo apt install -y mysql-router

# Bootstrap — reads cluster metadata and generates config
sudo mysqlrouter --bootstrap clusteradmin@node1:3306 \
  --user=mysqlrouter \
  --conf-use-sockets \
  --directory /etc/mysqlrouter

# Start and enable
sudo systemctl start mysqlrouter
sudo systemctl enable mysqlrouter
```

### Configure Router Health Check & Timeouts

```ini
# Edit /etc/mysqlrouter/mysqlrouter.conf

[routing:primary]
bind_address = 0.0.0.0
bind_port = 6446
destinations = metadata-cache://MyCluster/?role=PRIMARY
routing_strategy = first-available
protocol = classic

# How fast Router detects primary is down (seconds)
connect_timeout = 5
client_connect_timeout = 9

[routing:secondary]
bind_address = 0.0.0.0
bind_port = 6447
destinations = metadata-cache://MyCluster/?role=SECONDARY
routing_strategy = round-robin-with-fallback
protocol = classic
connect_timeout = 5
client_connect_timeout = 9

[metadata_cache:MyCluster]
router_id = 1
bootstrap_server_addresses = mysql://node1:3306,mysql://node2:3306,mysql://node3:3306

# How often Router checks cluster health (seconds)
ttl = 0.5

# Restart Router after editing
sudo systemctl restart mysqlrouter
```

> **💡 TTL = 0.5**  
> Router checks cluster health every 0.5 seconds. Lower = faster failover detection.  
> Default is 5 seconds — too slow for production.

---

## STEP 11 — Tune Failover Speed

**Why:** Default settings are too slow for production. These settings control exactly how fast the cluster detects a failure and elects a new primary.

```sql
-- Run on ALL 3 nodes
mysql -u clusteradmin -p

-- 1. How long before expelling an unresponsive node (seconds)
--    Lower = faster failover, but risk of false positives on slow networks
SET PERSIST group_replication_member_expel_timeout = 5;

-- 2. How long to wait for majority contact before giving up
--    0 = fail immediately if majority unreachable
SET PERSIST group_replication_unreachable_majority_timeout = 10;

-- 3. What this node does when it cannot stay in the cluster
--    READ_ONLY = stays up, refuses writes (safest for production)
--    ABORT_SERVER = crashes MySQL (ensures clean failover, aggressive)
SET PERSIST group_replication_exit_state_action = 'READ_ONLY';

-- 4. Consistency during failover
--    BEFORE_ON_PRIMARY_FAILOVER = new primary waits for all pending
--    transactions before accepting writes (prevents stale reads)
SET PERSIST group_replication_consistency = 'BEFORE_ON_PRIMARY_FAILOVER';
```

### Failover Timeline After Tuning

```
T+0  sec  → node1 crashes
T+5  sec  → node2 and node3 expel node1 (expel_timeout = 5)
T+8  sec  → new primary elected (node2)
T+9  sec  → MySQL Router detects change (TTL = 0.5, checks every 0.5s)
T+10 sec  → application writes rerouted to node2 ✅
```

---

## STEP 12 — Tune Auto-Rejoin

**Why:** When a node comes back after a crash, these settings control how aggressively it tries to rejoin, and what it does if it cannot.

```sql
-- Run on ALL 3 nodes

-- How many times to attempt rejoining (0 = disabled)
SET PERSIST group_replication_autorejoin_tries = 3;

-- Seconds to wait between each rejoin attempt
SET PERSIST group_replication_autorejoin_delay = 60;

-- What node does WHILE waiting to rejoin
-- Ensures node stays in safe read-only state during recovery window
SET PERSIST super_read_only = ON;

-- After all rejoin attempts fail, what to do:
-- READ_ONLY = node stays up but refuses writes
-- ABORT_SERVER = MySQL shuts down (forces DBA to investigate)
SET PERSIST group_replication_exit_state_action = 'READ_ONLY';
```

### Auto-Rejoin Flow

```
node1 crashes
  ↓
node1 MySQL restarts (systemd auto-restart or manual)
  ↓
group_replication_autorejoin_tries kicks in
  ↓
Attempt 1: try to rejoin cluster
  → success? → node1 is ONLINE as SECONDARY ✅
  → fail?    → wait 60 seconds (autorejoin_delay)
  ↓
Attempt 2: try to rejoin cluster
  → success? → node1 is ONLINE as SECONDARY ✅
  → fail?    → wait 60 seconds
  ↓
Attempt 3: try to rejoin cluster
  → success? → node1 is ONLINE as SECONDARY ✅
  → fail?    → apply exit_state_action (READ_ONLY or ABORT_SERVER)
```

---

## STEP 13 — Split-Brain Protection

**Why:** A network partition can split 3 nodes into groups that cannot communicate. Without protection, two nodes might both think they are the primary and accept conflicting writes — this is called split-brain and causes data corruption.

```sql
-- Run on ALL 3 nodes

-- How long a node waits to hear from majority before acting
-- If majority is unreachable after this time, node goes to exit_state_action
SET PERSIST group_replication_unreachable_majority_timeout = 10;

-- Prevent a minority partition from accepting writes
-- With READ_ONLY exit action, a node that loses quorum goes read-only
SET PERSIST group_replication_exit_state_action = 'READ_ONLY';
```

### Split-Brain Scenario Explained

```
Normal:
  node1 (Primary) ←──── network ────► node2
                                  ────► node3

Network partition:
  node1 ✅  (isolated, cannot reach node2, node3)
  node2 ✅  (has quorum: 2/3)
  node3 ✅  (has quorum: 2/3)

Without protection:
  node1 thinks: "I am still primary!" → accepts writes ❌ DATA CORRUPTION

With protection (exit_state_action = READ_ONLY):
  node1 loses majority contact after 10 sec
  node1 goes READ_ONLY automatically ✅
  node2 becomes new primary ✅
  No split-brain ✅
```

---

## STEP 14 — Monitoring

**Why:** You need to know the health of your cluster at all times. These queries show real-time status of all members and replication lag.

### Check Cluster Member Status

```sql
-- Shows all members and their current state
SELECT
  MEMBER_ID,
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,    -- ONLINE, RECOVERING, UNREACHABLE, OFFLINE, ERROR
  MEMBER_ROLE      -- PRIMARY, SECONDARY
FROM performance_schema.replication_group_members;
```

### Check Replication Lag

```sql
-- Shows how far behind each secondary is
SELECT
  MEMBER_ID,
  MEMBER_HOST,
  COUNT_TRANSACTIONS_IN_QUEUE,      -- transactions waiting to apply
  COUNT_TRANSACTIONS_CHECKED,
  COUNT_CONFLICTS_DETECTED,
  TRANSACTIONS_COMMITTED_ALL_MEMBERS
FROM performance_schema.replication_group_member_stats;
```

### Check Auto-Rejoin Status

```sql
-- Is auto-rejoin currently running?
SELECT * FROM performance_schema.events_stages_current
WHERE EVENT_NAME LIKE '%auto-rejoin%';
```

### Quick Health Check Script

```bash
#!/bin/bash
# Save as /usr/local/bin/cluster-health.sh
# Run: bash cluster-health.sh

mysql -u clusteradmin -pStrongPassword123! -e "
SELECT
  MEMBER_HOST,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;
"
```

### Monitor with MySQL Shell

```js
// Connect and watch status
mysqlsh clusteradmin@node1:3306

var cluster = dba.getCluster()

// Full status
cluster.status()

// Extended status with more detail
cluster.status({ extended: true })

// Watch topology
cluster.describe()
```

---

## Failover — Full Reference

### Automatic Failover (no action needed)

```
node1 crashes
  ↓ (5 sec expel timeout)
node2 & node3 vote → elect node2 as primary
  ↓ (Router detects in 0.5 sec)
App traffic → node2 automatically
  ↓
node3 stays as secondary
```

### Manual Failover (planned maintenance)

```js
mysqlsh clusteradmin@node1:3306
var cluster = dba.getCluster()

// Graceful switch (node1 must be ONLINE)
cluster.setPrimaryInstance('clusteradmin@node2:3306')

cluster.status()
// node2 is now PRIMARY
```

### Force Failover (primary unresponsive, not dead)

```js
// If primary is hanging but not fully dead
cluster.forceQuorumUsingPartitionOf('clusteradmin@node2:3306')
```

---

## Rejoin — Full Reference

### Option A — Auto-Rejoin (configured in Step 12)

```bash
# Just start MySQL — auto-rejoin handles the rest
sudo systemctl start mysql

# Monitor progress
mysql -u clusteradmin -p -e "
SELECT MEMBER_HOST, MEMBER_STATE
FROM performance_schema.replication_group_members;"
```

### Option B — Manual Rejoin

```js
mysqlsh clusteradmin@node2:3306   // connect to current primary

var cluster = dba.getCluster()
cluster.status()                   // confirm node1 shows MISSING

cluster.rejoinInstance('clusteradmin@node1:3306')

cluster.status()                   // node1 should be ONLINE
```

### Option C — Node Has Too Much Lag (needs full resync)

```js
// Remove the lagging node first
cluster.removeInstance('clusteradmin@node1:3306', { force: true })

// Re-add with Clone to do a full fresh sync
cluster.addInstance('clusteradmin@node1:3306', {
  recoveryMethod: 'clone'
})
```

### Option D — Full Cluster Recovery (ALL nodes were down)

```js
// Connect to node with most recent data
mysqlsh clusteradmin@node2:3306

// Reboot entire cluster
dba.rebootClusterFromCompleteOutage()

// Rejoin remaining nodes
var cluster = dba.getCluster()
cluster.rejoinInstance('clusteradmin@node1:3306')
cluster.rejoinInstance('clusteradmin@node3:3306')

cluster.status()
```

> **⚠️ WARNING**  
> Only run `rebootClusterFromCompleteOutage()` when ALL nodes were down at the same time.  
> Running it on a healthy partial cluster causes data inconsistency.

---

## Quick Reference Commands

| Task | Command |
|---|---|
| Check cluster status | `cluster.status()` |
| Detailed status | `cluster.status({ extended: true })` |
| Get cluster object | `var cluster = dba.getCluster()` |
| Add a new node | `cluster.addInstance('admin@nodeX:3306')` |
| Rejoin a node | `cluster.rejoinInstance('admin@nodeX:3306')` |
| Remove a node | `cluster.removeInstance('admin@nodeX:3306')` |
| Manual failover | `cluster.setPrimaryInstance('admin@node2:3306')` |
| Force quorum | `cluster.forceQuorumUsingPartitionOf('admin@node2:3306')` |
| Full recovery | `dba.rebootClusterFromCompleteOutage()` |
| Describe topology | `cluster.describe()` |

---

## Port Reference

| Port  | Used By           | Purpose                             |
|-------|-------------------|-------------------------------------|
| 3306  | MySQL Server      | Standard MySQL client connections   |
| 33061 | Group Replication | Internal node-to-node communication |
| 6446  | MySQL Router      | Read/Write → PRIMARY                |
| 6447  | MySQL Router      | Read Only → SECONDARY (round-robin) |

---

## Production Settings Summary

| Setting | Recommended Value | Why |
|---|---|---|
| `group_replication_member_expel_timeout` | `5` | Detect dead node in 5 sec |
| `group_replication_unreachable_majority_timeout` | `10` | Give up waiting for majority after 10 sec |
| `group_replication_exit_state_action` | `READ_ONLY` | Safe — node stays up but refuses writes |
| `group_replication_autorejoin_tries` | `3` | Retry joining 3 times before giving up |
| `group_replication_autorejoin_delay` | `60` | Wait 1 min between retries |
| `group_replication_consistency` | `BEFORE_ON_PRIMARY_FAILOVER` | No stale reads after failover |
| `mysqlrouter TTL` | `0.5` | Router checks health every 0.5 sec |

---

## Final Health Checklist

```
✅ cluster.status() shows: OK
✅ All 3 nodes: status ONLINE
✅ node1: mode R/W  (Primary)
✅ node2: mode R/O  (Secondary)
✅ node3: mode R/O  (Secondary)
✅ MySQL Router running on port 6446 and 6447
✅ autorejoin_tries = 3 on all nodes
✅ exit_state_action = READ_ONLY on all nodes
✅ Clone plugin ACTIVE on all nodes
✅ Router TTL = 0.5
✅ Monitoring queries returning data from performance_schema
```