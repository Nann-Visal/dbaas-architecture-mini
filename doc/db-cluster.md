
innodb is cluster mamang from buildin mysql?

9:06 AM
Yes! InnoDB Cluster is built into MySQL — it's MySQL's native high availability solution.

Here's a quick breakdown:

What's included (all built-in):

InnoDB — the default storage engine in MySQL (handles transactions, row-level locking, crash recovery)
MySQL Group Replication — built-in plugin for synchronous multi-primary replication
MySQL InnoDB Cluster — combines Group Replication + MySQL Shell + MySQL Router into a complete HA solution
Components:

MySQL Shell — the admin tool to set up and manage the cluster (dba.createCluster(), etc.)
MySQL Router — routes application connections to the right node (primary/secondary)
Group Replication — keeps data in sync across nodes automatically
So yes — no third-party software needed. Everything ships with MySQL 8.0+ (MySQL Shell and Router are separate downloads from the same MySQL team, but free and official).

Minimum setup: 3 nodes (for quorum/fault tolerance)

Quick comparison with alternatives:

Solution	Built-in?
InnoDB Cluster	✅ Yes (MySQL native)
Galera Cluster	❌ No (third-party, used by MariaDB/Percona)
Percona XtraDB	❌ No (Percona fork)
So if you're using standard MySQL, InnoDB Cluster is the go-to built-in clustering option.

if we has 2 node 
1. node primary
2. node standby
can we use this innodb to control
1. fialover
2. rejoin ?

9:08 AM
Yes, technically you can use InnoDB Cluster with 2 nodes, but there are important limitations you need to know:

⚠️ The Problem with 2 Nodes
InnoDB Cluster requires a quorum (majority vote) to function. With 2 nodes:

Quorum needs 2/2 nodes to agree
If 1 node goes down → cluster loses quorum → no automatic failover
So with 2 nodes alone, automatic failover won't work reliably.

✅ The Solution — Use MySQL Router as a "voter"
You can add a 3rd lightweight member to solve quorum without a full MySQL node:

Option 1: mysqlrouter as a quorum voter
Not directly, but you can use:

Option 2: MySQL InnoDB ClusterSet or add a "MySQL Clone" instance
Option 3 (Best for 2 nodes): Add a Replica with memberWeight
Use a MySQL instance running as a quorum-only node (very lightweight):

sql
-- Set one node as low weight (won't become primary)
dba.rebootClusterFromCompleteOutage()
What Works with 2 Nodes
Feature	2 Nodes	Notes
Failover (auto)	❌ Risky	No quorum if 1 node down
Failover (manual)	✅ Yes	cluster.setPrimaryInstance()
Rejoin	✅ Yes	cluster.rejoinInstance()
Replication sync	✅ Yes	Works fine
Rejoin — How it works ✅
When a node comes back online after failure:

js
// In MySQL Shell
var cluster = dba.getCluster();
cluster.rejoinInstance('user@node2:3306');
Or set auto-rejoin:

sql
SET PERSIST group_replication_autorejoin_tries = 3;
```

---

## Recommendation

For **production HA with true automatic failover**, use **3 nodes minimum**:
```
Node 1 — Primary
Node 2 — Secondary  
Node 3 — Secondary (can be lightweight/cheap server)
If budget is tight, Node 3 can just be a small VM acting as a tiebreaker.

Summary: 2 nodes = rejoin ✅, manual failover ✅, but automatic failover ❌ without a 3rd quorum member.

if three node?

9:11 AM
With 3 nodes, InnoDB Cluster works perfectly and gives you full automatic failover + rejoin! ✅

3-Node InnoDB Cluster Architecture
┌─────────────────────────────────────────────┐
│              MySQL Router                    │
│         (routes app connections)             │
└──────────┬──────────────┬───────────────────┘
           │              │
    Write/Read          Read
           │              │
┌──────────▼──────┐  ┌───▼────────────┐  ┌────────────────┐
│   Node 1        │  │   Node 2        │  │   Node 3       │
│   PRIMARY       │◄─►  SECONDARY     │◄─►  SECONDARY     │
│   (R/W)         │  │   (Read only)   │  │  (Read only)   │
└─────────────────┘  └─────────────────┘  └────────────────┘
     Group Replication (synchronous sync all nodes)
✅ Failover with 3 Nodes
Quorum = 2 out of 3 nodes → if 1 node dies, cluster still has quorum and continues automatically.

Scenario: Primary (Node 1) goes down
Before:
  Node1 = PRIMARY  ✅
  Node2 = Secondary ✅
  Node3 = Secondary ✅

Node1 crashes ❌

After (automatic, ~5-30 seconds):
  Node1 = OFFLINE  ❌
  Node2 = PRIMARY  ✅  ← auto-elected
  Node3 = Secondary ✅
No manual action needed! MySQL Router automatically reroutes traffic to new primary.

✅ Rejoin with 3 Nodes
When Node1 comes back online:

Auto Rejoin (recommended)
sql
-- Set this on each node before starting
SET PERSIST group_replication_autorejoin_tries = 3;
Node automatically tries to rejoin the cluster.

Manual Rejoin (MySQL Shell)
js
var cluster = dba.getCluster();

// Check cluster status first
cluster.status();

// Rejoin the instance
cluster.rejoinInstance('admin@node1:3306');
Full Feature Table — 3 Nodes
Feature	Status	Details
Auto Failover	✅ Full	Elects new primary in ~5-30 sec
Manual Failover	✅ Yes	cluster.setPrimaryInstance()
Auto Rejoin	✅ Yes	Via autorejoin_tries
Manual Rejoin	✅ Yes	cluster.rejoinInstance()
Quorum tolerance	✅ 1 node	Can lose 1 node safely
Read scale-out	✅ Yes	Route reads to secondaries
Data sync	✅ Sync	All nodes always in sync
Useful MySQL Shell Commands
js
// Connect
mysqlsh admin@node1:3306

// Get cluster
var cluster = dba.getCluster();

// Check status
cluster.status();

// Manual failover (switch primary)
cluster.setPrimaryInstance('admin@node2:3306');

// Rejoin a node
cluster.rejoinInstance('admin@node1:3306');

// If cluster lost quorum (2+ nodes down at same time)
dba.rebootClusterFromCompleteOutage();
Summary
Scenario	2 Nodes	3 Nodes
Auto failover	❌	✅
Manual failover	✅	✅
Rejoin	✅	✅
Lose 1 node safely	❌	✅
3 nodes is the sweet spot — minimum for full production-grade HA with InnoDB Cluster! 🎯

what is this Quorum

9:11 AM
Quorum — Simple Explanation
Quorum = "majority vote" to make a decision

Think of it like a committee that needs majority agreement before doing anything important.

Simple Analogy 🗳️
Imagine 3 judges in a courtroom:

Judge 1 ✅  →  "Node 1 is dead, promote Node 2!"
Judge 2 ✅  →  "I agree!"
Judge 3 ❌  →  (missing/offline)

Result: 2 out of 3 agree = MAJORITY = decision made ✅
If only 1 judge shows up → can't make a decision → no quorum

Why Quorum Exists — The "Split-Brain" Problem
Without quorum, a dangerous situation called Split-Brain can happen:

Network partition occurs ↓

Node1 (Primary) thinks: "Node2 & 3 are dead, I'm still primary!"
Node2 thinks:           "Node1 is dead, I'm the new primary!"

Now TWO nodes think they're primary
→ Both accept writes
→ DATA CORRUPTION 💥
Quorum prevents this — only the side with majority can act.

Quorum Formula
Quorum = (Total Nodes / 2) + 1

2 nodes → need 2/2 = 2   (both must be alive)
3 nodes → need 3/2 = 2   (any 2 must be alive)
4 nodes → need 4/2 = 3   (any 3 must be alive)
5 nodes → need 5/2 = 3   (any 3 must be alive)
Visual — 3 Node Cluster
✅ Has Quorum (2/3 alive)
Node1 ✅ PRIMARY
Node2 ✅ SECONDARY    →  2 nodes agree = quorum ✅
Node3 ❌ DOWN              → auto failover works!
❌ No Quorum (1/3 alive)
Node1 ✅ SECONDARY
Node2 ❌ DOWN          →  only 1 node = no quorum ❌
Node3 ❌ DOWN              → cluster FREEZES, no failover
What Happens When Quorum is Lost?
Cluster FREEZES completely:
  ❌ No writes accepted
  ❌ No automatic failover
  ❌ No new elections
  
  → Must manually recover:
  dba.rebootClusterFromCompleteOutage();
Why 3 Nodes is Minimum for HA
Nodes	Can lose	Quorum needed
1	0 nodes	not HA
2	0 nodes	both must be up
3	1 node	2 must be up ✅
4	1 node	3 must be up
5	2 nodes	3 must be up ✅
💡 Odd numbers (3, 5, 7) are better — they tolerate more failures per node added compared to even numbers.

Summary
Term	Meaning
Quorum	Majority of nodes must agree
Purpose	Prevent split-brain / data corruption
Formula	(n/2) + 1 nodes must be alive
Lost quorum	Cluster freezes, manual recovery needed
Simple rule: Always use odd number of nodes (3, 5, 7) for best fault tolerance! 🎯

so please give me step step by step for this implement if we have 3 node. and explain each step

9:13 AM
Let me create a comprehensive step-by-step guide document for you!


Check available skills
Check available skills
Now let me create the comprehensive step-by-step guide:


Ran 2 commands, created a file, read a file
Ran 2 commands, created a file, read a file
Here's your complete step-by-step guide! Here's a summary of the 10 steps covered:

Step	What You Do
1	Install MySQL 8.0 on all 3 nodes
2	Configure /etc/hosts so nodes find each other
3	Set up my.cnf with Group Replication settings
4	Create a cluster admin user on all nodes
5	Install MySQL Shell on node1
6	Check & auto-fix each node's configuration
7	Create the InnoDB Cluster (node1 becomes PRIMARY)
8	Add node2 and node3 to complete the cluster
9	Install & bootstrap MySQL Router
10	Enable auto-rejoin on all nodes
The guide also includes full sections on how failover works step-by-step, 3 ways to rejoin a node (auto, manual, full recovery), and a quick reference command table.

Mysql innodb cluster 3node guide
Document · DOCX 
why we use etc host ? not ip

9:20 AM
Good question! Here's the simple reason:

Why Hostname, Not IP?
1. 🔒 InnoDB Cluster Stores Hostnames Internally
When you run dba.createCluster(), MySQL records the hostname (not IP) in its internal metadata tables:

sql
SELECT * FROM mysql_innodb_cluster_metadata.instances;
-- Stores: 'node1:3306', 'node2:3306', 'node3:3306'
```

If you used IPs instead, it stores IPs — and that causes problems when IPs change.

---

### 2. 🔄 IP Can Change, Hostname Stays the Same
```
Today:    node1 = 192.168.1.11  ✅
Tomorrow: node1 = 192.168.1.50  (IP changed after reboot/DHCP)

With hostname → just update /etc/hosts → cluster still works ✅
With IP       → cluster metadata is wrong → nodes can't find each other ❌
```

---

### 3. 📖 Easier to Read & Manage
```
# Hard to remember:
cluster.addInstance('admin@192.168.1.12:3306')

# Easy to understand:
cluster.addInstance('admin@node2:3306')
4. ✅ SSL Certificate Compatibility
If you use SSL/TLS, certificates are issued to hostnames, not IPs. Using hostnames keeps everything consistent.

Can You Use IP Instead?
Yes, technically — but only if:

Your IPs are static and never change
You set group_replication_local_address to the IP
All cluster metadata uses IPs consistently
But most DBAs prefer hostnames because it's safer long-term.

Summary
Hostname (/etc/hosts)	IP Address
IP changes	✅ Just update hosts file	❌ Cluster breaks
Readable	✅ node1, node2, node3	❌ Hard to remember
SSL certs	✅ Compatible	⚠️ Extra config needed
Production safe	✅ Recommended	⚠️ Risky
Simple rule: Use hostnames → your cluster survives infrastructure changes. 🎯

please give me as md fomart

9:22 AM

Created a file, read a file
Created a file, read a file
Here's the .md file! Same content as before, formatted as clean Markdown with code blocks, tables, and sections ready to use in any docs system (GitHub, Notion, Obsidian, etc.).

Why hostname not ip
Document · MD 
no, step  of configuration mysql cluster as md formart

9:25 AM

Created a file, read a file
Created a file, read a file
Here's the full 3-node MySQL InnoDB Cluster setup guide in .md format! It includes all 10 steps, failover explanation, rejoin options, and quick reference tables — ready to use in GitHub, Notion, Obsidian, or any markdown viewer.

Mysql innodb cluster 3node guide
Document · MD 
this complete auto rejoin and fialover?

9:40 AM
No, the guide covers the basics but is not fully complete for production. Here is what is missing:

What the Guide Covers ✅
Basic auto-rejoin (autorejoin_tries)
Basic automatic failover (Group Replication election)
Manual rejoin and manual failover commands
What is Missing for Production ❌
1. Failover Tuning
The guide does not cover how fast failover happens:

sql
-- How long before a node is declared dead (default: 5 sec)
SET PERSIST group_replication_member_expel_timeout = 5;

-- How long to wait before starting election
SET PERSIST group_replication_unreachable_majority_timeout = 0;

-- Auto-elect new primary when old one dies
SET PERSIST group_replication_exit_state_action = 'ABORT_SERVER';
2. Failover with MySQL Router — Health Check
The guide does not cover Router health check intervals:

ini
# /etc/mysqlrouter/mysqlrouter.conf
[routing:primary]
connect_timeout = 5
client_connect_timeout = 9
3. Auto-Rejoin Edge Cases
The guide does not cover what happens if auto-rejoin fails all retries:

sql
-- What node does when it cannot rejoin after all tries
-- Options: READ_ONLY, OFFLINE_MODE, ABORT_SERVER
SET PERSIST group_replication_exit_state_action = 'READ_ONLY';
4. Clone Plugin for Large Data Sync
When rejoining a node with lots of missed data, the guide does not cover enabling the Clone plugin:

sql
INSTALL PLUGIN clone SONAME 'mysql_clone.so';
GRANT BACKUP_ADMIN ON *.* TO 'clusteradmin'@'%';
5. Monitoring
No monitoring coverage — in production you need to watch:

sql
-- Check group replication status in real time
SELECT * FROM performance_schema.replication_group_members;
SELECT * FROM performance_schema.replication_group_member_stats;
6. Split-Brain Protection
The guide does not cover what happens if network partitions into two equal halves — this needs group_replication_unreachable_majority_timeout.

Summary
Topic	Guide	Complete?
Basic auto-rejoin	✅	Basic only
Basic failover	✅	Basic only
Failover speed tuning	❌	Missing
Router health check	❌	Missing
Rejoin failure handling	❌	Missing
Clone plugin setup	❌	Missing
Monitoring	❌	Missing
Split-brain protection	❌	Missing
Do you want me to update the guide with all the missing production settings? 🎯

yes

9:42 AM

Created a file, read a file
Created a file, read a file
Here's the complete production guide! Here's what was added compared to the previous version:

Added	What It Covers
Step 5	Clone plugin install — fast data sync on rejoin
Step 11	Failover speed tuning — expel timeout, consistency level
Step 12	Auto-rejoin tuning — retry delay, exit state, full rejoin flow
Step 13	Split-brain protection — unreachable majority timeout
Step 14	Monitoring — real-time member status, replication lag, health script
Rejoin D	Full cluster recovery when all nodes were down simultaneously
Production settings table	All recommended values with explanations
Final checklist	10-point health check to confirm everything is working
Mysql innodb cluster complete guide
Document · MD 





Claude is AI and can make mistakes. Please double-check responses.
Mysql innodb cluster complete guide · MD
Copy

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
