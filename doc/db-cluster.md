╔═══════════════════════════════════════════════════════════════════════════════╗
║                              APPLICATIONS                                     ║
║                                                                               ║
║        [ App A ]         [ App B ]         [ App C ]         [ App D ]        ║
╚═══════════════════════════════════════════════════════════════════════════════╝
                                      │
                                      │  All apps connect to ONE IP
                                      ▼
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║                        VIP  10.10.78.100 : all ports                          ║
║                     (Virtual IP managed by Keepalived)                        ║
║                   Always alive — even if HAProxy VM 1 dies                    ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
                                      │
                    ┌─────────────────┴─────────────────┐
                    │       Keepalived splits VIP       │
                    │       to whoever is ACTIVE        │
                    ▼                                   ▼
╔═════════════════════════════╗         ╔═════════════════════════════╗
║   HAProxy VM 1  10.10.78.125║         ║  HAProxy VM 2  10.10.78.126 ║
║        [ ACTIVE ]           ║◄───────►║       [ PASSIVE ]           ║
║                             ║ heartbt ║                             ║
║  HAProxy (traffic router)   ║         ║  HAProxy (traffic router)   ║
║  ── MySQL A      :25010     ║         ║  ── MySQL A      :25010     ║
║  ── MySQL B      :25011     ║         ║  ── MySQL B      :25011     ║
║  ── PostgreSQL A :25013     ║         ║  ── PostgreSQL A :25013     ║
║  ── PostgreSQL B :25014     ║         ║  ── PostgreSQL B :25014     ║
║  ── Redis A      :25015     ║         ║  ── Redis A      :25015     ║
║  ── Redis B      :25016     ║         ║  ── Redis B      :25016     ║
║  ── MongoDB A    :25017     ║         ║  ── MongoDB A    :25017     ║
║  ── MongoDB B    :25018     ║         ║  ── MongoDB B    :25018     ║
║  ── Stats        :8404      ║         ║  ── Stats        :8404      ║
║                             ║         ║                             ║
║  Orchestrator (MySQL HA)    ║◄───────►║  Orchestrator (MySQL HA)    ║
║  port 3000  [ Raft sync ]   ║  raft   ║  port 3000  [ Raft sync ]   ║
╚═════════════════════════════╝         ╚═════════════════════════════╝
          │                                           │
          └────────────────────────┬──────────────────┘
                                   │
                                   │  HAProxy routes each port to correct DB cluster
                                   │
       ┌───────────────────────────┼───────────┬─────────────────┐
       │                    │                  │                 │
       ▼                    ▼                  ▼                 ▼
╔══════════════╗   ╔══════════════╗    ╔══════════════╗   ╔══════════════╗
║  MySQL Layer ║   ║  PostgreSQL  ║    ║  Redis Layer ║   ║ MongoDB Layer║
║              ║   ║    Layer     ║    ║              ║   ║              ║
║  Cluster A   ║   ║  Cluster A   ║    ║  Cluster A   ║   ║  Cluster A   ║
║  ┌─────────┐ ║   ║  ┌─────────┐ ║    ║  ┌─────────┐ ║   ║  ┌─────────┐ ║
║  │ PRIMARY │ ║   ║  │ PRIMARY │ ║    ║  │ PRIMARY │ ║   ║  │ PRIMARY │ ║
║  │.108.152 │ ║   ║  │.108.160 │ ║    ║  │.108.170 │ ║   ║  │.108.180 │ ║
║  │  :3306  │ ║   ║  │  :5432  │ ║    ║  │  :6379  │ ║   ║  │ :27017  │ ║
║  └────┬────┘ ║   ║  └────┬────┘ ║    ║  └────┬────┘ ║   ║  └────┬────┘ ║
║       │ GTID ║   ║       │stream║    ║       │ repl ║   ║       │ repl ║
║       │ repl ║   ║       │ repl ║    ║       │      ║   ║       │      ║
║  ┌────▼────┐ ║   ║  ┌────▼────┐ ║    ║  ┌────▼────┐ ║   ║  ┌────▼────┐ ║
║  │ REPLICA │ ║   ║  │ REPLICA │ ║    ║  │ REPLICA │ ║   ║  │ REPLICA │ ║
║  │.100.183 │ ║   ║  │.100.190 │ ║    ║  │.100.195 │ ║   ║  │.100.200 │ ║
║  │  :3306  │ ║   ║  │  :5432  │ ║    ║  │  :6379  │ ║   ║  │ :27017  │ ║
║  └─────────┘ ║   ║  └─────────┘ ║    ║  └─────────┘ ║   ║  └─────────┘ ║
║              ║   ║              ║    ║              ║   ║              ║
║  Cluster B   ║   ║  Cluster B   ║    ║  Cluster B   ║   ║  Cluster B   ║
║  ┌─────────┐ ║   ║  ┌─────────┐ ║    ║  ┌─────────┐ ║   ║  ┌─────────┐ ║
║  │ PRIMARY │ ║   ║  │ PRIMARY │ ║    ║  │ PRIMARY │ ║   ║  │ PRIMARY │ ║
║  │.108.153 │ ║   ║  │.108.161 │ ║    ║  │.108.171 │ ║   ║  │.108.181 │ ║
║  │  :3306  │ ║   ║  │  :5432  │ ║    ║  │  :6379  │ ║   ║  │ :27017  │ ║
║  └────┬────┘ ║   ║  └────┬────┘ ║    ║  └────┬────┘ ║   ║  └────┬────┘ ║
║       │ GTID ║   ║       │stream║    ║       │ repl ║   ║       │ repl ║
║  ┌────▼────┐ ║   ║  ┌────▼────┐ ║    ║  ┌────▼────┐ ║   ║  ┌────▼────┐ ║
║  │ REPLICA │ ║   ║  │ REPLICA │ ║    ║  │ REPLICA │ ║   ║  │ REPLICA │ ║
║  │.100.184 │ ║   ║  │.100.191 │ ║    ║  │.100.196 │ ║   ║  │.100.201 │ ║
║  │  :3306  │ ║   ║  │  :5432  │ ║    ║  │  :6379  │ ║   ║  │ :27017  │ ║
║  └─────────┘ ║   ║  └─────────┘ ║    ║  └─────────┘ ║   ║  └─────────┘ ║
║              ║   ║              ║    ║              ║   ║              ║
║ HA Manager:  ║   ║ HA Manager:  ║    ║ HA Manager:  ║   ║ HA Manager:  ║
║ Orchestrator ║   ║   Patroni    ║    ║  Sentinel    ║   ║ ReplicaSet   ║
║              ║   ║              ║    ║              ║   ║              ║
║ Health Check ║   ║ Health Check ║    ║ Health Check ║   ║ Health Check ║
║ mysql-check  ║   ║ HTTP :8008   ║    ║ role:master  ║   ║ HTTP :8009   ║
║              ║   ║ /primary     ║    ║  tcp-check   ║   ║ /primary     ║
║              ║   ║              ║    ║              ║   ║              ║
║ Failover:    ║   ║ Failover:    ║    ║ Failover:    ║   ║ Failover:    ║
║    ~15s      ║   ║    ~10s      ║    ║    ~10s      ║   ║    ~10s      ║
╚══════════════╝   ╚══════════════╝    ╚══════════════╝   ╚══════════════╝
       │                  │                  │                   │
       └──────────────────┴──────────────────┴───────────────────┘
                                      │
                                      │  All exporters scrape metrics
                                      ▼
                    ╔══════════════════════════════════╗
                    ║     Monitoring VM 10.10.78.140   ║
                    ║                                  ║
                    ║  Prometheus      port 9090       ║
                    ║  ── mysql_exporter    :9104      ║
                    ║  ── postgres_exporter :9187      ║
                    ║  ── redis_exporter    :9121      ║
                    ║  ── mongodb_exporter  :9216      ║
                    ║  ── haproxy_exporter  :9101      ║
                    ║                                  ║
                    ║  Grafana         port 3000       ║
                    ║  ── All DB dashboards            ║
                    ║  ── HAProxy dashboard            ║
                    ║  ── Replication lag alerts       ║
                    ║                                  ║
                    ║  Alertmanager    port 9093       ║
                    ║  ── Slack                        ║
                    ║  ── PagerDuty                    ║
                    ║  ── Email                        ║
                    ╚══════════════════════════════════╝


MySQL Cluster A                    MySQL Cluster B
─────────────────                  ─────────────────
Primary  10.10.108.152:3306        Primary  10.10.108.153:3306
Replica  10.10.100.183:3306        Replica  10.10.100.184:3306
Manager  Orchestrator              Manager  Orchestrator

PostgreSQL Cluster A               PostgreSQL Cluster B
─────────────────                  ─────────────────
Primary  10.10.108.160:5432        Primary  10.10.108.161:5432
Replica  10.10.100.190:5432        Replica  10.10.100.191:5432
Manager  Patroni                   Manager  Patroni

Redis Cluster A                    Redis Cluster B
─────────────────                  ─────────────────
Primary  10.10.108.170:6379        Primary  10.10.108.171:6379
Replica  10.10.100.195:6379        Replica  10.10.100.196:6379
Manager  Redis Sentinel            Manager  Redis Sentinel

MongoDB Cluster A                  MongoDB Cluster B
─────────────────                  ─────────────────
Primary  10.10.108.180:27017       Primary  10.10.108.181:27017
Replica  10.10.100.200:27017       Replica  10.10.100.201:27017
Manager  Mongo ReplicaSet          Manager  Mongo ReplicaSet




#---------------------------------------------------------------------
# Global
#---------------------------------------------------------------------
global
    log         /dev/log local0
    log         /dev/log local1 notice
    chroot      /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin expose-fd listeners
    stats timeout 30s
    user        haproxy
    group       haproxy
    daemon
    maxconn     50000
    nbthread    4

#---------------------------------------------------------------------
# Defaults
#---------------------------------------------------------------------
defaults
    log         global
    mode        tcp
    option      tcplog
    option      dontlognull
    option      redispatch
    retries     3
    timeout connect     5s
    timeout client      60s
    timeout server      60s
    timeout check       2s
    maxconn     20000

#---------------------------------------------------------------------
# Stats Dashboard
# Access: http://10.10.78.125:8404/stats
#---------------------------------------------------------------------
frontend stats
    bind                *:8404
    mode                http
    stats enable
    stats uri           /stats
    stats realm         HAProxy\ Statistics
    stats auth          admin:YourStatsPassword!
    stats refresh       10s
    stats show-legends
    stats show-node
    acl trusted_ip      src 10.10.0.0/16
    http-request deny   if !trusted_ip

#=====================================================================
# MYSQL CLUSTERS
#=====================================================================

#---------------------------------------------------------------------
# MySQL Cluster A — port 25010
#---------------------------------------------------------------------
frontend mysql_cluster_a
    bind                *:25010
    mode                tcp
    option              tcplog
    default_backend     mysql_back_a

backend mysql_back_a
    mode                tcp
    option              tcp-check
    option              mysql-check user haproxy_check post-41
    balance             first
    default-server      inter 3s rise 2 fall 3 on-marked-down shutdown-sessions
    server  mysql-primary-a  10.10.108.152:3306  check weight 100
    server  mysql-replica-a  10.10.100.183:3306  check weight 1 backup

#---------------------------------------------------------------------
# MySQL Cluster B — port 25011
#---------------------------------------------------------------------
frontend mysql_cluster_b
    bind                *:25011
    mode                tcp
    option              tcplog
    default_backend     mysql_back_b

backend mysql_back_b
    mode                tcp
    option              tcp-check
    option              mysql-check user haproxy_check post-41
    balance             first
    default-server      inter 3s rise 2 fall 3 on-marked-down shutdown-sessions
    server  mysql-primary-b  10.10.108.153:3306  check weight 100
    server  mysql-replica-b  10.10.100.184:3306  check weight 1 backup

#=====================================================================
# POSTGRESQL CLUSTERS
#=====================================================================

#---------------------------------------------------------------------
# PostgreSQL Cluster A — port 25013
#---------------------------------------------------------------------
frontend pgsql_cluster_a
    bind                *:25013
    mode                tcp
    option              tcplog
    default_backend     pgsql_back_a

backend pgsql_back_a
    mode                tcp
    option              tcp-check
    option              httpchk GET /primary
    http-check expect   status 200
    balance             first
    default-server      inter 3s rise 2 fall 3 on-marked-down shutdown-sessions
    server  pgsql-primary-a  10.10.108.160:5432  check port 8008 weight 100
    server  pgsql-replica-a  10.10.100.190:5432  check port 8008 weight 1 backup

#---------------------------------------------------------------------
# PostgreSQL Cluster B — port 25014
#---------------------------------------------------------------------
frontend pgsql_cluster_b
    bind                *:25014
    mode                tcp
    option              tcplog
    default_backend     pgsql_back_b

backend pgsql_back_b
    mode                tcp
    option              tcp-check
    option              httpchk GET /primary
    http-check expect   status 200
    balance             first
    default-server      inter 3s rise 2 fall 3 on-marked-down shutdown-sessions
    server  pgsql-primary-b  10.10.108.161:5432  check port 8008 weight 100
    server  pgsql-replica-b  10.10.100.191:5432  check port 8008 weight 1 backup

#=====================================================================
# REDIS CLUSTERS
#=====================================================================

#---------------------------------------------------------------------
# Redis Cluster A — port 25015
#---------------------------------------------------------------------
frontend redis_cluster_a
    bind                *:25015
    mode                tcp
    option              tcplog
    default_backend     redis_back_a

backend redis_back_a
    mode                tcp
    option              tcp-check
    tcp-check           send PING\r\n
    tcp-check           expect string +PONG
    tcp-check           send info\ replication\r\n
    tcp-check           expect string role:master
    tcp-check           send QUIT\r\n
    tcp-check           expect string +OK
    balance             first
    default-server      inter 3s rise 2 fall 3 on-marked-down shutdown-sessions
    server  redis-primary-a  10.10.108.170:6379  check weight 100
    server  redis-replica-a  10.10.100.195:6379  check weight 1 backup

#---------------------------------------------------------------------
# Redis Cluster B — port 25016
#---------------------------------------------------------------------
frontend redis_cluster_b
    bind                *:25016
    mode                tcp
    option              tcplog
    default_backend     redis_back_b

backend redis_back_b
    mode                tcp
    option              tcp-check
    tcp-check           send PING\r\n
    tcp-check           expect string +PONG
    tcp-check           send info\ replication\r\n
    tcp-check           expect string role:master
    tcp-check           send QUIT\r\n
    tcp-check           expect string +OK
    balance             first
    default-server      inter 3s rise 2 fall 3 on-marked-down shutdown-sessions
    server  redis-primary-b  10.10.108.171:6379  check weight 100
    server  redis-replica-b  10.10.100.196:6379  check weight 1 backup

#=====================================================================
# MONGODB CLUSTERS
#=====================================================================

#---------------------------------------------------------------------
# MongoDB Cluster A — port 25017
#---------------------------------------------------------------------
frontend mongo_cluster_a
    bind                *:25017
    mode                tcp
    option              tcplog
    default_backend     mongo_back_a

backend mongo_back_a
    mode                tcp
    option              tcp-check
    balance             first
    default-server      inter 3s rise 2 fall 3 on-marked-down shutdown-sessions
    server  mongo-primary-a  10.10.108.180:27017  check weight 100
    server  mongo-replica-a  10.10.100.200:27017  check weight 1 backup

#---------------------------------------------------------------------
# MongoDB Cluster B — port 25018
#---------------------------------------------------------------------
frontend mongo_cluster_b
    bind                *:25018
    mode                tcp
    option              tcplog
    default_backend     mongo_back_b

backend mongo_back_b
    mode                tcp
    option              tcp-check
    balance             first
    default-server      inter 3s rise 2 fall 3 on-marked-down shutdown-sessions
    server  mongo-primary-b  10.10.108.181:27017  check weight 100
    server  mongo-replica-b  10.10.100.201:27017  check weight 1 backup
```

---

## HA Manager Per DB Type
```
┌──────────────────────────────────────────────────────────┐
│               HA Manager Responsibilities                │
├──────────┬───────────────┬──────────────────────────────┤
│ DB Type  │ HA Manager    │ Failover Trigger             │
├──────────┼───────────────┼──────────────────────────────┤
│ MySQL    │ Orchestrator  │ Auto via hooks → HAProxy     │
│ MariaDB  │ Orchestrator  │ Auto via hooks → HAProxy     │
│ PgSQL    │ Patroni       │ Auto via REST API → HAProxy  │
│ Redis    │ Sentinel      │ Auto promotes master         │
│ MongoDB  │ ReplicaSet    │ Auto elects primary          │
└──────────┴───────────────┴──────────────────────────────┘
```

---

## Health Check Per DB Type
```
MySQL    → option mysql-check user haproxy_check post-41
PgSQL    → HTTP check Patroni REST API port 8008 /primary → 200 OK
Redis    → tcp-check PING → PONG + role:master
MongoDB  → tcp-check TCP connect port 27017
```

---

## Failover Flow Per DB Type
```
MYSQL FAILOVER
──────────────
Primary down (9-15s detected by HAProxy)
        │
        ▼
Orchestrator detects → promotes replica
        │
        ▼
failover.sh → HAProxy Runtime API
        │
        ▼
Traffic → new primary ✅

POSTGRESQL FAILOVER
───────────────────
Primary down (9-15s detected by HAProxy)
        │
        ▼
Patroni detects → promotes replica
        │
        ▼
Patroni updates REST API /primary endpoint
        │
        ▼
HAProxy health check fails on old primary
        │
        ▼
HAProxy routes to new primary ✅
(No script needed — Patroni + HTTP check handles it)

REDIS FAILOVER
──────────────
Primary down
        │
        ▼
Redis Sentinel votes (needs 3 sentinels)
        │
        ▼
Sentinel promotes replica to master
        │
        ▼
HAProxy tcp-check detects role:master changed
        │
        ▼
Traffic → new master ✅
(No script needed — tcp-check role:master handles it)

MONGODB FAILOVER
────────────────
Primary down
        │
        ▼
ReplicaSet election (automatic ~10s)
        │
        ▼
New primary elected
        │
        ▼
HAProxy TCP check routes to new primary ✅
(No script needed — ReplicaSet handles it internally)
```

---

## Port Map — Full Reference
```
┌──────────┬──────────────────────────┬───────┬──────────────┐
│ DB Type  │ Cluster                  │ Port  │ HA Manager   │
├──────────┼──────────────────────────┼───────┼──────────────┤
│ MySQL    │ Cluster A                │ 25010 │ Orchestrator │
│ MySQL    │ Cluster B                │ 25011 │ Orchestrator │
│ MySQL    │ Cluster C                │ 25012 │ Orchestrator │
│ PgSQL    │ Cluster A                │ 25013 │ Patroni      │
│ PgSQL    │ Cluster B                │ 25014 │ Patroni      │
│ Redis    │ Cluster A                │ 25015 │ Sentinel     │
│ Redis    │ Cluster B                │ 25016 │ Sentinel     │
│ MongoDB  │ Cluster A                │ 25017 │ ReplicaSet   │
│ MongoDB  │ Cluster B                │ 25018 │ ReplicaSet   │
│ HAProxy  │ Stats Dashboard          │  8404 │ -            │
│ Orchstr  │ Web UI                   │  3000 │ -            │
│ Patroni  │ REST API                 │  8008 │ -            │
└──────────┴──────────────────────────┴───────┴──────────────┘
```

---

## Monitoring Stack (Standard DBaaS)
```
┌─────────────────────────────────────────────┐
│            Monitoring Stack                 │
├─────────────────────────────────────────────┤
│                                             │
│  Prometheus  ← scrapes all DB metrics       │
│       │                                     │
│       ▼                                     │
│  Grafana     ← visualize dashboards         │
│       │                                     │
│       ▼                                     │
│  Alertmanager → PagerDuty / Slack / Email   │
│                                             │
│  Exporters per DB type:                     │
│  mysql_exporter      → port 9104            │
│  postgres_exporter   → port 9187            │
│  redis_exporter      → port 9121            │
│  mongodb_exporter    → port 9216            │
│  haproxy_exporter    → port 9101            │
└─────────────────────────────────────────────┘
```

---

## Summary — What Makes This Standard
```
✅ Single HAProxy entry point    — one VM manages all DB traffic
✅ Separate port per cluster     — full traffic isolation
✅ Correct HA tool per DB type   — Orchestrator/Patroni/Sentinel/ReplicaSet
✅ Correct health check per DB   — mysql-check/http-check/tcp-check
✅ Auto failover per DB type     — no manual intervention needed
✅ Zero cross-cluster impact     — cluster A down = others unaffected
✅ Monitoring per DB type        — Prometheus exporters
✅ Single dashboard              — HAProxy stats + Grafana
✅ Scalable                      — add new cluster = add frontend/backend block