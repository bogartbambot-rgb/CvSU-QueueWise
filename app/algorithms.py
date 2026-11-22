"""Transparent, independently testable ADTs used by QueueWise.

SQLite is durable storage. These data structures are reconstructed from the current
transaction snapshot; they are not confused with database B-tree indexes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable


@dataclass
class _Node:
    value: str
    next: '_Node | None' = None


class ArrivalQueue:
    """Singly linked FIFO arrival log; processing does not erase history."""

    def __init__(self):
        self.head: _Node | None = None
        self.tail: _Node | None = None
        self.length = 0

    def enqueue(self, value: str) -> None:
        node = _Node(value)
        if self.tail is None:
            self.head = node
        else:
            self.tail.next = node
        self.tail = node
        self.length += 1

    def front(self) -> str | None:
        return None if self.head is None else self.head.value

    def dequeue(self) -> str | None:
        if self.head is None:
            return None
        value = self.head.value
        self.head = self.head.next
        if self.head is None:
            self.tail = None
        self.length -= 1
        return value

    def is_empty(self) -> bool:
        return self.length == 0

    def traverse(self) -> list[str]:
        result = []
        cursor = self.head
        while cursor is not None:
            result.append(cursor.value)
            cursor = cursor.next
        return result


class SeparateChainingHashTable:
    """Custom hash index with buckets, collisions and automatic resizing."""

    def __init__(self, capacity: int = 8):
        self.capacity = max(4, capacity)
        self.buckets: list[list[tuple[str, Any]]] = [[] for _ in range(self.capacity)]
        self.size = 0

    def _index(self, key: str) -> int:
        # Stable FNV-1a, rather than Python's randomized hash().
        value = 2166136261
        for b in key.encode('utf-8'):
            value = ((value ^ b) * 16777619) & 0xffffffff
        return value % self.capacity

    def _resize(self) -> None:
        entries = [(key, value) for bucket in self.buckets for key, value in bucket]
        self.capacity *= 2
        self.buckets = [[] for _ in range(self.capacity)]
        self.size = 0
        for key, value in entries:
            self.put(key, value)

    def put(self, key: str, value: Any) -> None:
        bucket = self.buckets[self._index(key)]
        for i, (existing, _) in enumerate(bucket):
            if existing == key:
                raise ValueError('Duplicate request ID')
        bucket.append((key, value))
        self.size += 1
        if self.size / self.capacity > 0.75:
            self._resize()

    def get(self, key: str) -> Any | None:
        for existing, value in self.buckets[self._index(key)]:
            if existing == key:
                return value
        return None

    def contains(self, key: str) -> bool:
        return any(k == key for k, _ in self.buckets[self._index(key)])

    def update(self, key: str, value: Any) -> None:
        bucket = self.buckets[self._index(key)]
        for i, (existing, _) in enumerate(bucket):
            if existing == key:
                bucket[i] = (existing, value)
                return
        raise KeyError(key)


class MinHeap:
    """Binary min-heap storing (priority key, request_id) pairs."""

    def __init__(self):
        self.items: list[tuple[tuple[Any, ...], str]] = []

    def is_empty(self) -> bool:
        return not self.items

    def peek(self) -> str | None:
        return self.items[0][1] if self.items else None

    def insert(self, key: tuple, request_id: str) -> None:
        self.items.append((key, request_id))
        self._sift_up(len(self.items) - 1)

    def _sift_up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) // 2
            if self.items[parent][0] <= self.items[i][0]:
                return
            self.items[i], self.items[parent] = self.items[parent], self.items[i]
            i = parent

    def _sift_down(self, i: int) -> None:
        length = len(self.items)
        while True:
            left, right = 2 * i + 1, 2 * i + 2
            smallest = i
            if left < length and self.items[left][0] < self.items[smallest][0]:
                smallest = left
            if right < length and self.items[right][0] < self.items[smallest][0]:
                smallest = right
            if smallest == i:
                return
            self.items[i], self.items[smallest] = self.items[smallest], self.items[i]
            i = smallest

    def heapify(self, entries: Iterable[tuple[tuple, str]]) -> None:
        self.items = list(entries)
        for index in range(len(self.items) // 2 - 1, -1, -1):
            self._sift_down(index)

    def extract_min(self) -> str | None:
        if not self.items:
            return None
        result = self.items[0][1]
        last = self.items.pop()
        if self.items:
            self.items[0] = last
            self._sift_down(0)
        return result

    def ranked_copy(self) -> list[str]:
        """Sorting a snapshot never damages the actual heap."""
        return [request_id for _, request_id in sorted(self.items)]

    def valid(self) -> bool:
        return all(self.items[(i-1)//2][0] <= self.items[i][0] for i in range(1, len(self.items)))


CATEGORIES = {'Graduating': 100, 'Job Applicant': 60, 'Regular': 20}
DOCUMENT_TYPES = ('Transcript of Records (TOR)', 'Certificate of Grades', 'Good Moral Certificate')
STATUSES = ('Pending', 'Processing', 'Ready for Release', 'Processed')


def calculate_score(record: dict, today: date) -> float:
    """Group-proposed weighted score, NOT an official institutional priority policy.

    PS = 0.50*U + 0.30*W + 0.20*C, with every term on a 0..100 scale.
    """
    submitted = date.fromisoformat(record['submission_date'])
    deadline = date.fromisoformat(record['deadline'])
    if today < submitted:
        raise ValueError('Simulation date cannot precede submission date')
    days_left = max(0, (deadline - today).days)
    days_waited = max(0, (today - submitted).days)
    urgency = 100.0 * max(0.0, 1.0 - days_left / 30.0)
    waiting = 100.0 * min(1.0, days_waited / 10.0)
    category = CATEGORIES[record['category']]
    return 0.50 * urgency + 0.30 * waiting + 0.20 * category


def priority_key(record: dict) -> tuple:
    # Stable order: highest score, closest deadline, earliest arrival, ID.
    return (-record['priority_score'], record['deadline'], record['arrival_number'], record['public_id'])


class QueueEngine:
    """Builds demonstrable linear and nonlinear ADTs from SQLite records."""

    def __init__(self, records: list[dict]):
        self.records = records
        self.arrivals = ArrivalQueue()
        self.hash_table = SeparateChainingHashTable()
        self.heap = MinHeap()
        for record in sorted(records, key=lambda rec: rec['arrival_number']):
            self.arrivals.enqueue(record['public_id'])
            self.hash_table.put(record['public_id'], record)
        self._rebuild_heap()

    def add_record(self, record: dict) -> None:
        """Perform all three submission ADT operations on a new record."""
        if self.hash_table.contains(record['public_id']):
            raise ValueError('Duplicate request ID')
        if self.records and record['arrival_number'] <= max(r['arrival_number'] for r in self.records):
            raise ValueError('Arrival number must increase monotonically')
        self.records.append(record)
        self.arrivals.enqueue(record['public_id'])
        self.hash_table.put(record['public_id'], record)
        if record['status'] == 'Pending' and not record.get('cancelled_at') and not record.get('declined_at'):
            self.heap.insert(priority_key(record), record['public_id'])

    def _rebuild_heap(self) -> None:
        self.heap.heapify(
            (priority_key(record), record['public_id'])
            for record in self.records if record['status'] == 'Pending' and not record.get('cancelled_at') and not record.get('declined_at')
        )

    def refresh(self, today: date) -> None:
        for record in self.records:
            if record['status'] == 'Pending' and not record.get('cancelled_at') and not record.get('declined_at'):
                record['priority_score'] = calculate_score(record, today)
        self._rebuild_heap()

    def ranked(self) -> list[dict]:
        return [self.hash_table.get(public_id) for public_id in self.heap.ranked_copy()]

    def process_next(self) -> dict | None:
        public_id = self.heap.extract_min()
        if public_id is None:
            return None
        record = self.hash_table.get(public_id)
        record['status'] = 'Processed'
        self.hash_table.update(public_id, record)
        return record
