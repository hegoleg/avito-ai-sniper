"""
Verification Queue & Anti-ban Protection Module.

Implements:
1. InspectionStatus enum: Lifecycle states for Avito listing verification.
2. QueuedItem dataclass: Enqueued candidate representation with priority and metadata.
3. VerificationQueue class: Deduplication store, TTL caching, price drop detection,
   and multi-tier priority sorting for candidate listings.
4. Randomized pause jitter and exponential backoff utilities for anti-ban resilience.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("verification_queue")


class InspectionStatus(str, Enum):
    """
    Status of an Avito listing in the verification pipeline.

    Inherits from str for seamless serialization and string comparison:
        InspectionStatus.VERIFIED_DEAL == "VERIFIED_DEAL" -> True
    """
    UNINSPECTED = "UNINSPECTED"
    VERIFIED_DEAL = "VERIFIED_DEAL"
    REJECTED_STATIC = "REJECTED_STATIC"      # Permanent defects, mobile GPU chips, bait accessories
    REJECTED_RESERVED = "REJECTED_RESERVED"  # Currently in Avito reserve / delivery


@dataclass
class QueuedItem:
    """
    Listing candidate enqueued for deep verification.

    Priorities:
        1: Fresh listings from s=104 never inspected
        2: Price drops on known listings
        3: Cheap baseline listings from s=1 never inspected
        4: Periodic re-validation / expired TTL
    """
    item_id: str
    item_dict: dict = field(repr=False, compare=False)
    source_sort: str = "104"  # "104" (newest) or "1" (cheapest)
    price: int = 0
    priority: int = 1
    discovered_at: float = field(default_factory=time.time, compare=False)

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, QueuedItem):
            return NotImplemented
        # Primary: priority ASC (1 is highest), Secondary: price ASC, Tertiary: discovered_at ASC
        return (self.priority, self.price, self.discovered_at) < (
            other.priority,
            other.price,
            other.discovered_at,
        )


class VerificationQueue:
    """
    Smart verification queue and deduplication store.

    Maintains listing inspection states, prevents duplicate browser tab
    inspections, prioritizes fresh discoveries, and detects price drops.
    """

    def __init__(
        self,
        cache_ttl_seconds: int = 7200,
        reserved_ttl_seconds: int = 1800,
        cache_file: Optional[str] = None,
    ):
        """
        Initialize VerificationQueue.

        Args:
            cache_ttl_seconds: TTL for verified deals before re-checking (default 2 hours / 7200s).
            reserved_ttl_seconds: TTL for reserved items before re-checking (default 30 min / 1800s).
            cache_file: Optional path to JSON persistence cache file.
        """
        self.cache_ttl = int(cache_ttl_seconds)
        self.reserved_ttl = int(reserved_ttl_seconds)
        self.cache_file = cache_file
        # In-memory deduplication store: item_id -> {status, price, inspected_at, reason}
        self.item_states: Dict[str, Dict[str, Any]] = {}

        if self.cache_file and os.path.exists(self.cache_file):
            self.load_from_json(self.cache_file)

    @staticmethod
    def _clean_price(price_val: Any) -> int:
        """Helper to extract clean integer price from integer, float, or string."""
        if price_val is None:
            return 0
        if isinstance(price_val, (int, float)):
            try:
                return int(price_val)
            except (ValueError, OverflowError):
                return 0
        if isinstance(price_val, str):
            digits = "".join(ch for ch in price_val if ch.isdigit())
            if digits:
                try:
                    return int(digits)
                except (ValueError, OverflowError):
                    return 0
        return 0

    def should_inspect(self, item_id: Union[str, int], current_price: Union[int, float, str]) -> bool:
        """
        Determines whether a listing should undergo deep page inspection.

        Rules:
        1. Returns True if unseen.
        2. Returns False for REJECTED_STATIC (permanent defects, mobile chips, accessories).
        3. Returns True if current_price < prev_price (price drop re-inspection).
        4. Returns False for VERIFIED_DEAL within cache_ttl (default 7200s / 2 hours).
        5. Returns False for REJECTED_RESERVED within reserved_ttl (default 1800s / 30 minutes).
        6. Returns True otherwise (TTL expired or uninspected status).
        """
        str_id = str(item_id)
        if str_id not in self.item_states:
            return True

        record = self.item_states[str_id]
        status = record.get("status")
        prev_price = record.get("price", 0)
        inspected_at = record.get("inspected_at", 0.0)
        cur_p = self._clean_price(current_price)

        # 1. Permanent rejection (defects, mobile chips, bait accessories) is never re-inspected
        if status == InspectionStatus.REJECTED_STATIC or status == "REJECTED_STATIC":
            return False

        # 2. Price drop re-inspection on known items
        if cur_p > 0 and prev_price > 0 and cur_p < prev_price:
            return True

        now = time.time()

        # 3. Verified deals: skip within cache_ttl
        if status == InspectionStatus.VERIFIED_DEAL or status == "VERIFIED_DEAL":
            if (now - inspected_at) < self.cache_ttl:
                return False
            return True

        # 4. Reserved listings: skip within reserved_ttl
        if status == InspectionStatus.REJECTED_RESERVED or status == "REJECTED_RESERVED":
            if (now - inspected_at) < self.reserved_ttl:
                return False
            return True

        # 5. Explicitly UNINSPECTED or unrecognized status
        if status == InspectionStatus.UNINSPECTED or status == "UNINSPECTED":
            return True

        return True

    def record_result(
        self,
        item_id: Union[str, int],
        status: Union[InspectionStatus, str],
        price: Union[int, float, str],
        reason: str = "",
    ) -> None:
        """
        Record or update the verification inspection result for an item.

        Args:
            item_id: Avito listing identifier.
            status: InspectionStatus or matching string.
            price: Current listing price.
            reason: Optional explanation (e.g. rejection reason or spec match).
        """
        str_id = str(item_id)
        if isinstance(status, str):
            try:
                status = InspectionStatus(status)
            except ValueError:
                pass

        p_int = self._clean_price(price)
        self.item_states[str_id] = {
            "status": status,
            "price": p_int,
            "inspected_at": time.time(),
            "reason": str(reason or ""),
        }

        if self.cache_file:
            self._save_cache_safely()

    def prioritize_queue(
        self,
        items_104: Optional[List[dict]] = None,
        items_1: Optional[List[dict]] = None,
        max_count: Optional[int] = 7,
    ) -> List[QueuedItem]:
        """
        Prioritize listings from s=104 (newest) and s=1 (cheapest) into an ordered QueuedItem queue.

        Priorities:
            - Priority 1: Fresh items from s=104 never inspected
            - Priority 2: Price drops on known items
            - Priority 3: Uninspected cheap baseline items from s=1
            - Priority 4: Periodic re-validation (TTL expired on verified/reserved deals)

        Returns:
            List of QueuedItem sorted by (priority ASC, price ASC, discovered_at ASC)
            truncated to max_count (or all if max_count is None).
        """
        list_104 = items_104 or []
        list_1 = items_1 or []

        candidates_map: Dict[str, QueuedItem] = {}

        # 1. Process items from s=104 (Fresh listings)
        for it in list_104:
            if not isinstance(it, dict):
                continue
            item_id = it.get("item_id")
            if not item_id:
                continue
            str_id = str(item_id)
            price = self._clean_price(it.get("price"))

            if not self.should_inspect(str_id, price):
                continue

            # Determine priority tier
            if (
                str_id not in self.item_states
                or self.item_states[str_id].get("status") in (InspectionStatus.UNINSPECTED, "UNINSPECTED")
            ):
                priority = 1  # Fresh s=104 never inspected
            else:
                prev_price = self.item_states[str_id].get("price", 0)
                if price > 0 and prev_price > 0 and price < prev_price:
                    priority = 2  # Price drop on known item
                else:
                    priority = 4  # Re-inspection / expired TTL

            candidates_map[str_id] = QueuedItem(
                item_id=str_id,
                item_dict=it,
                source_sort="104",
                price=price,
                priority=priority,
                discovered_at=time.time(),
            )

        # 2. Process items from s=1 (Cheapest baseline)
        for it in list_1:
            if not isinstance(it, dict):
                continue
            item_id = it.get("item_id")
            if not item_id:
                continue
            str_id = str(item_id)
            price = self._clean_price(it.get("price"))

            if not self.should_inspect(str_id, price):
                continue

            if str_id in candidates_map:
                # Already captured from s=104. Keep the highest priority (lowest number)
                existing = candidates_map[str_id]
                if price > 0 and (existing.price <= 0 or price < existing.price):
                    existing.price = price
                continue

            # Determine priority tier for s=1
            if (
                str_id not in self.item_states
                or self.item_states[str_id].get("status") in (InspectionStatus.UNINSPECTED, "UNINSPECTED")
            ):
                priority = 3  # Uninspected cheap baseline from s=1
            else:
                prev_price = self.item_states[str_id].get("price", 0)
                if price > 0 and prev_price > 0 and price < prev_price:
                    priority = 2  # Price drop on known item
                else:
                    priority = 4  # Re-inspection / expired TTL

            candidates_map[str_id] = QueuedItem(
                item_id=str_id,
                item_dict=it,
                source_sort="1",
                price=price,
                priority=priority,
                discovered_at=time.time(),
            )

        # 3. Sort by (priority ASC, price ASC, discovered_at ASC)
        sorted_queue = sorted(
            candidates_map.values(),
            key=lambda q: (q.priority, q.price, q.discovered_at),
        )

        if max_count is not None:
            if max_count <= 0:
                return []
            return sorted_queue[:max_count]

        return sorted_queue

    def prioritize_candidates(
        self,
        items_104: Optional[List[dict]] = None,
        items_1: Optional[List[dict]] = None,
        max_count: int = 7,
    ) -> List[dict]:
        """
        Sorts candidate queue by (priority ASC, price ASC) and returns top max_count item dicts.

        Args:
            items_104: Items collected from sort_by="104" (newest first).
            items_1: Items collected from sort_by="1" (cheapest first).
            max_count: Maximum candidate count to inspect (default 7).

        Returns:
            List[dict] containing the top candidate item dicts.
        """
        queued = self.prioritize_queue(items_104=items_104, items_1=items_1, max_count=max_count)
        result: List[dict] = []
        for q in queued:
            d = q.item_dict
            # Annotate with queue priority metadata for transparency
            d["_queue_priority"] = q.priority
            d["_source_sort"] = q.source_sort
            result.append(d)
        return result

    def get_status(self, item_id: Union[str, int]) -> Optional[InspectionStatus]:
        """Get status for an item_id if present."""
        str_id = str(item_id)
        record = self.item_states.get(str_id)
        if record:
            st = record.get("status")
            if isinstance(st, InspectionStatus):
                return st
            try:
                return InspectionStatus(st)
            except ValueError:
                return None
        return None

    def clear(self) -> None:
        """Clear all in-memory item states."""
        self.item_states.clear()
        if self.cache_file and os.path.exists(self.cache_file):
            try:
                os.remove(self.cache_file)
            except OSError:
                pass

    def get_stats(self) -> Dict[str, int]:
        """Returns statistical breakdown of inspected items."""
        stats = {
            "total_tracked": len(self.item_states),
            "verified_deal": 0,
            "rejected_static": 0,
            "rejected_reserved": 0,
            "uninspected": 0,
            "other": 0,
        }
        for rec in self.item_states.values():
            st = rec.get("status")
            val = st.value if isinstance(st, InspectionStatus) else str(st)
            if val == InspectionStatus.VERIFIED_DEAL.value:
                stats["verified_deal"] += 1
            elif val == InspectionStatus.REJECTED_STATIC.value:
                stats["rejected_static"] += 1
            elif val == InspectionStatus.REJECTED_RESERVED.value:
                stats["rejected_reserved"] += 1
            elif val == InspectionStatus.UNINSPECTED.value:
                stats["uninspected"] += 1
            else:
                stats["other"] += 1
        return stats

    def save_to_json(self, filepath: str) -> None:
        """Saves deduplication cache to a JSON file."""
        data: Dict[str, Any] = {}
        for k, v in self.item_states.items():
            st = v.get("status")
            st_str = st.value if isinstance(st, InspectionStatus) else str(st)
            data[k] = {
                "status": st_str,
                "price": v.get("price", 0),
                "inspected_at": v.get("inspected_at", 0.0),
                "reason": v.get("reason", ""),
            }
        tmp_path = f"{filepath}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)

    def load_from_json(self, filepath: str) -> None:
        """Loads deduplication cache from a JSON file."""
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                st_str = v.get("status")
                try:
                    status = InspectionStatus(st_str)
                except ValueError:
                    status = st_str
                self.item_states[k] = {
                    "status": status,
                    "price": int(v.get("price", 0)),
                    "inspected_at": float(v.get("inspected_at", 0.0)),
                    "reason": str(v.get("reason", "")),
                }
        except Exception as e:
            logger.warning("Failed to load verification cache from %s: %s", filepath, e)

    def _save_cache_safely(self) -> None:
        if not self.cache_file:
            return
        try:
            self.save_to_json(self.cache_file)
        except Exception as e:
            logger.warning("Failed to persist verification cache: %s", e)

    def __len__(self) -> int:
        return len(self.item_states)

    def __contains__(self, item_id: Any) -> bool:
        return str(item_id) in self.item_states


# ---------------------------------------------------------------------------
# Anti-ban Randomized Pause & Backoff Utilities
# ---------------------------------------------------------------------------

async def async_sleep_jitter(base_sec: float, jitter_pct: float = 0.20) -> float:
    """
    Sleeps with randomized jitter (e.g. base_sec +/- jitter_pct).
    Example: 60s with 0.20 jitter -> random duration between 48.0s and 72.0s.

    Args:
        base_sec: Base sleep duration in seconds.
        jitter_pct: Percentage jitter relative to base_sec (default 0.20 = +/-20%).

    Returns:
        The exact randomized duration slept in seconds.
    """
    if base_sec <= 0:
        await asyncio.sleep(0)
        return 0.0

    jitter = max(0.0, min(1.0, float(jitter_pct)))
    min_sec = max(0.0, base_sec * (1.0 - jitter))
    max_sec = base_sec * (1.0 + jitter)
    duration = random.uniform(min_sec, max_sec)
    await asyncio.sleep(duration)
    return duration


async def async_request_pause(min_sec: float = 1.8, max_sec: float = 3.5) -> float:
    """
    Randomized pause between web requests, searches, or tab loads.

    Args:
        min_sec: Minimum pause in seconds (default 1.8s).
        max_sec: Maximum pause in seconds (default 3.5s).

    Returns:
        The exact randomized duration slept in seconds.
    """
    if max_sec < min_sec:
        min_sec, max_sec = max_sec, min_sec
    duration = random.uniform(min_sec, max_sec)
    await asyncio.sleep(duration)
    return duration


class BackoffManager:
    """
    Adaptive exponential backoff manager with randomized jitter.

    Used when rate-limited (HTTP 429/439), challenged by GeeTest sliders,
    or encountering access restrictions.
    """

    def __init__(
        self,
        base_delay: float = 30.0,
        max_delay: float = 600.0,
        jitter_min: float = 3.0,
        jitter_max: float = 10.0,
    ):
        """
        Initialize BackoffManager.

        Args:
            base_delay: Starting delay in seconds on first error (default 30.0s).
            max_delay: Maximum delay ceiling in seconds (default 600.0s / 10 min).
            jitter_min: Minimum random jitter added in seconds (default 3.0s).
            jitter_max: Maximum random jitter added in seconds (default 10.0s).
        """
        self.base_delay = float(base_delay)
        self.max_delay = float(max_delay)
        self.jitter_min = float(jitter_min)
        self.jitter_max = float(jitter_max)
        self.consecutive_errors: int = 0
        self.last_delay: float = 0.0

    def record_error(self) -> float:
        """
        Record a failure/challenge and return exponential backoff delay with random jitter.

        Calculation:
            delay = min(max_delay, base_delay * 2^(errors - 1)) + random_jitter
            capped at max_delay.
        """
        self.consecutive_errors += 1
        # Cap exponent to avoid overflow (up to 2^5 = 32x base)
        exponent = min(self.consecutive_errors - 1, 5)
        factor = 2 ** exponent
        jitter = random.uniform(self.jitter_min, self.jitter_max)
        calculated = (self.base_delay * factor) + jitter
        delay = min(self.max_delay, calculated)
        self.last_delay = delay
        return delay

    def record_success(self) -> None:
        """Record a successful operation and reset consecutive error counter."""
        self.consecutive_errors = 0
        self.last_delay = 0.0

    def reset(self) -> None:
        """Alias for record_success."""
        self.record_success()

    async def async_wait(self) -> float:
        """Record error, sleep for the computed backoff duration, and return the duration."""
        delay = self.record_error()
        await asyncio.sleep(delay)
        return delay

    @property
    def is_backing_off(self) -> bool:
        """Returns True if currently in backoff state."""
        return self.consecutive_errors > 0

    @property
    def current_delay(self) -> float:
        """Returns the most recently computed delay."""
        return self.last_delay
