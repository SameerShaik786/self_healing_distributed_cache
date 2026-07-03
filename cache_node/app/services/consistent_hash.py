import hashlib
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class ConsistentHash:
    """
    Consistent hashing for distributed key distribution.
    Ensures minimal key movement when nodes join/leave.
    """

    def __init__(self, nodes: List[str], replicas: int = 2):
        """
        Initialize consistent hash ring.
        
        Args:
            nodes: List of node IDs
            replicas: Number of replicas per key (default 2 out of 3)
        """
        self.nodes = sorted(nodes)
        self.replicas = replicas
        self.ring = {}  # hash value -> node_id
        self.sorted_keys = []  # sorted hash values
        self._build_ring()

    def _hash(self, key: str) -> int:
        """Hash a key to an integer."""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def _build_ring(self) -> None:
        """Build the hash ring."""
        self.ring = {}
        
        # Create virtual nodes for better distribution
        for node in self.nodes:
            for i in range(160):  # 160 virtual nodes per physical node
                virtual_key = f"{node}:{i}"
                hash_value = self._hash(virtual_key)
                self.ring[hash_value] = node
        
        self.sorted_keys = sorted(self.ring.keys())
        logger.debug(f"Built ring with {len(self.ring)} virtual nodes")

    def get_replicas_for_key(self, key: str) -> List[str]:
        """
        Get replica nodes for a key.
        Returns list of node IDs in order.
        """
        if not self.ring:
            return []

        hash_value = self._hash(key)
        replicas = []
        
        # Find position in sorted keys
        idx = self._binary_search(hash_value)
        
        # Collect replicas (skip duplicates)
        for i in range(len(self.sorted_keys)):
            pos = (idx + i) % len(self.sorted_keys)
            node = self.ring[self.sorted_keys[pos]]
            
            if node not in replicas:
                replicas.append(node)
                if len(replicas) == self.replicas:
                    break
        
        return replicas

    def _binary_search(self, hash_value: int) -> int:
        """Binary search for position in sorted keys."""
        left, right = 0, len(self.sorted_keys) - 1
        
        while left <= right:
            mid = (left + right) // 2
            if self.sorted_keys[mid] < hash_value:
                left = mid + 1
            else:
                right = mid - 1
        
        return left % len(self.sorted_keys)

    def keys_to_move_on_join(self, new_node: str, all_keys: List[str]) -> Tuple[dict, dict]:
        """
        Calculate which keys move when a new node joins.
        Returns: (keys_to_move_from, keys_to_move_to)
        """
        # Rebuild ring with new node
        old_nodes = self.nodes
        new_nodes = sorted(old_nodes + [new_node])
        
        keys_from_old = {}  # {old_node: [keys]}
        keys_to_new = []
        
        for key in all_keys:
            old_replicas = self.get_replicas_for_key(key)
            
            # Temporarily update ring
            self.nodes = new_nodes
            self._build_ring()
            
            new_replicas = self.get_replicas_for_key(key)
            
            # Restore old ring
            self.nodes = old_nodes
            self._build_ring()
            
            # If new_node is in new replicas but not old, key moves to it
            if new_node in new_replicas and new_node not in old_replicas:
                keys_to_new.append(key)
                
                # Track which old node it comes from
                if old_replicas:
                    source_node = old_replicas[0]
                    if source_node not in keys_from_old:
                        keys_from_old[source_node] = []
                    keys_from_old[source_node].append(key)
        
        return keys_from_old, {"keys": keys_to_new, "destination": new_node}

    def keys_to_move_on_leave(self, removed_node: str, all_keys: List[str]) -> dict:
        """
        Calculate which keys need to move when a node leaves.
        Returns: {key: [destination_nodes]}
        """
        # Rebuild ring without the node
        old_nodes = self.nodes
        new_nodes = [n for n in self.nodes if n != removed_node]
        
        keys_to_move = {}
        
        for key in all_keys:
            old_replicas = self.get_replicas_for_key(key)
            
            # If removed_node had this key, find where it goes
            if removed_node in old_replicas:
                # Temporarily update ring
                self.nodes = new_nodes
                self._build_ring()
                
                new_replicas = self.get_replicas_for_key(key)
                
                # Restore old ring
                self.nodes = old_nodes
                self._build_ring()
                
                # Add destinations that don't already have it
                new_dests = [n for n in new_replicas if n not in old_replicas]
                if new_dests:
                    keys_to_move[key] = new_dests
        
        return keys_to_move

    def rebalance(self, new_nodes: List[str]) -> dict:
        """
        Calculate full rebalancing plan when cluster composition changes.
        Returns: {operation_type, keys_to_move, source_dest_pairs}
        """
        old_nodes = sorted(self.nodes)
        new_nodes = sorted(new_nodes)
        
        if old_nodes == new_nodes:
            return {"status": "no_change"}
        
        joined = [n for n in new_nodes if n not in old_nodes]
        left = [n for n in old_nodes if n not in new_nodes]
        
        return {
            "status": "rebalance_needed",
            "joined_nodes": joined,
            "left_nodes": left,
            "old_nodes": old_nodes,
            "new_nodes": new_nodes,
        }
