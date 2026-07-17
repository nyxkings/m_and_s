"""DRSRS topology: shards, replicas, regions, and consistent hashing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterable


class Domain(Enum):
    """Failure domains (correlated within a domain under disaster)."""

    CAMPUS_A = auto()
    CAMPUS_B = auto()
    CLOUD = auto()


class ReplicaRole(Enum):
    PRIMARY = auto()
    SYNC_REPLICA = auto()
    ASYNC_REGIONAL = auto()
    ASYNC_CLOUD = auto()


@dataclass
class Replica:
    """A single physical replica of a shard."""

    replica_id: str
    shard_id: int
    domain: Domain
    role: ReplicaRole
    up: bool = True
    # Version / last-write timestamp (sim hours) for CAP reconciliation
    last_write_time: float = 0.0

    def mark_down(self) -> None:
        self.up = False

    def mark_up(self) -> None:
        self.up = True


@dataclass
class Shard:
    """One hash-partition of the student-record keyspace."""

    shard_id: int
    replicas: list[Replica] = field(default_factory=list)

    def alive_replicas(self) -> list[Replica]:
        return [r for r in self.replicas if r.up]

    def has_reachable_replica(self) -> bool:
        return any(r.up for r in self.replicas)

    def all_down(self) -> bool:
        return all(not r.up for r in self.replicas)

    def replicas_in_domain(self, domain: Domain) -> list[Replica]:
        return [r for r in self.replicas if r.domain == domain]


@dataclass
class CoordinatorNode:
    node_id: int
    up: bool = True


@dataclass
class Topology:
    """Full DRSRS deployment topology across regions and cloud DR."""

    shards: list[Shard]
    coordinators: list[CoordinatorNode]
    n_shards: int
    k1: int
    k_regional: int
    k2: int

    def all_replicas(self) -> Iterable[Replica]:
        for sh in self.shards:
            yield from sh.replicas

    def shard_reachable_fraction(self) -> float:
        if not self.shards:
            return 0.0
        return sum(1 for s in self.shards if s.has_reachable_replica()) / len(self.shards)

    def system_db_up(self) -> bool:
        """True iff every shard has ≥1 reachable replica (report metric)."""
        return all(s.has_reachable_replica() for s in self.shards)

    def quorum_up(self) -> bool:
        n = len(self.coordinators)
        m = n // 2 + 1
        return sum(1 for c in self.coordinators if c.up) >= m


def consistent_hash_shard(matric_number: str, n_shards: int) -> int:
    """Map a matriculation number to a shard via consistent hashing (MD5 ring).

    Section 3.3: hash(matric) mod N, with MD5 providing uniform spread.
    (Full consistent-hash ring with virtual nodes is equivalent for fixed N.)
    """
    digest = hashlib.md5(matric_number.encode("utf-8")).hexdigest()
    return int(digest, 16) % n_shards


def build_topology(
    n_shards: int,
    k1: int,
    k_regional: int,
    k2: int,
    n_coordinators: int = 3,
) -> Topology:
    """Construct Level 0–3 DRSRS topology from Section 3.2.

    Per shard:
      - Campus A: 1 primary + (k1−1) sync replicas  (Level 0/1)
      - Campus B: k_regional async regional replicas (Level 2)
      - Cloud:    k2 async DR replicas               (Level 3)
    """
    if k1 < 1:
        raise ValueError("k1 (campus replicas) must be ≥ 1")
    shards: list[Shard] = []
    for sid in range(n_shards):
        replicas: list[Replica] = []
        # Campus A synchronous set
        for i in range(k1):
            role = ReplicaRole.PRIMARY if i == 0 else ReplicaRole.SYNC_REPLICA
            replicas.append(
                Replica(
                    replica_id=f"s{sid}-A{i}",
                    shard_id=sid,
                    domain=Domain.CAMPUS_A,
                    role=role,
                )
            )
        # Campus B regional async
        for i in range(k_regional):
            replicas.append(
                Replica(
                    replica_id=f"s{sid}-B{i}",
                    shard_id=sid,
                    domain=Domain.CAMPUS_B,
                    role=ReplicaRole.ASYNC_REGIONAL,
                )
            )
        # Cloud DR
        for i in range(k2):
            replicas.append(
                Replica(
                    replica_id=f"s{sid}-C{i}",
                    shard_id=sid,
                    domain=Domain.CLOUD,
                    role=ReplicaRole.ASYNC_CLOUD,
                )
            )
        shards.append(Shard(shard_id=sid, replicas=replicas))

    coords = [CoordinatorNode(node_id=i) for i in range(n_coordinators)]
    return Topology(
        shards=shards,
        coordinators=coords,
        n_shards=n_shards,
        k1=k1,
        k_regional=k_regional,
        k2=k2,
    )
