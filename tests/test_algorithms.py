from datetime import date
import pytest

from app.algorithms import (ArrivalQueue, SeparateChainingHashTable, MinHeap,
                            calculate_score, priority_key, QueueEngine)


def request(id_, arrival, category='Regular', deadline='2026-11-10', submission='2026-11-09'):
    return dict(public_id=id_, arrival_number=arrival, category=category,
                deadline=deadline, submission_date=submission,
                status='Pending', priority_score=0)


def test_fifo_operations_and_empty():
    queue = ArrivalQueue()
    assert queue.is_empty() and queue.front() is None and queue.dequeue() is None
    for number in range(120):
        queue.enqueue(f'REQ-{number:04d}')
    assert queue.front() == 'REQ-0000'
    assert queue.traverse()[10] == 'REQ-0010'
    assert [queue.dequeue() for _ in range(120)] == [f'REQ-{n:04d}' for n in range(120)]
    assert queue.is_empty() and queue.tail is None


def test_hash_collision_and_resize():
    table = SeparateChainingHashTable(capacity=4)
    for i in range(200):
        table.put(f'REQ-{i:04d}', {'n': i})
    assert table.capacity > 4
    assert table.size == 200
    for i in range(200):
        assert table.get(f'REQ-{i:04d}') == {'n': i}
    assert table.get('unknown') is None
    with pytest.raises(ValueError):
        table.put('REQ-0000', 999)
    table.update('REQ-0000', {'n': -1})
    assert table.get('REQ-0000')['n'] == -1
    assert table.contains('REQ-0199')
    with pytest.raises(KeyError):
        table.update('unknown', 'missing')


def test_minheap_insert_extract_heapify_and_copy():
    heap = MinHeap()
    for n in [9, 7, 1, 5, 3, 2, 4, 6, 8, 0]:
        heap.insert((n,), str(n))
    assert heap.valid()
    assert heap.peek() == '0'
    assert heap.ranked_copy() == [str(n) for n in range(10)]
    assert heap.peek() == '0'  # sorted view is non-destructive
    assert [heap.extract_min() for _ in range(10)] == [str(n) for n in range(10)]
    assert heap.extract_min() is None
    heap.heapify([((i,), str(i)) for i in range(100, -1, -1)])
    assert heap.valid()
    assert heap.extract_min() == '0'


def test_weighted_formula_matches_proposal_example():
    first = request('REQ-0001', 1, 'Graduating', '2026-11-15', '2026-11-08')
    second = request('REQ-0002', 2, 'Regular', '2026-11-10', '2026-11-09')
    assert round(calculate_score(first, date(2026, 11, 10)), 2) == 67.67
    assert round(calculate_score(second, date(2026, 11, 10)), 2) == 57.00
    assert 0 <= calculate_score(first, date(2026, 12, 1)) <= 100
    with pytest.raises(ValueError):
        calculate_score(first, date(2026, 11, 7))


def test_priorities_ties_and_fifo_history():
    rows = [
        request('REQ-0001', 1, 'Graduating', '2026-11-15', '2026-11-08'),
        request('REQ-0002', 2, 'Regular', '2026-11-10', '2026-11-09'),
        request('REQ-0003', 3, 'Job Applicant', '2026-11-10', '2026-11-09'),
    ]
    engine = QueueEngine(rows)
    engine.refresh(date(2026, 11, 10))
    assert engine.arrivals.traverse() == ['REQ-0001','REQ-0002','REQ-0003']
    assert [r['public_id'] for r in engine.ranked()] == ['REQ-0001','REQ-0003','REQ-0002']
    assert engine.heap.valid()
    root_before = engine.heap.peek()
    assert engine.ranked()[0]['public_id'] == root_before
    chosen = engine.process_next()
    assert chosen['public_id'] == 'REQ-0001'
    assert engine.hash_table.get('REQ-0001')['status'] == 'Processed'
    assert engine.arrivals.front() == 'REQ-0001'
    assert engine.heap.peek() == 'REQ-0003'


def test_tie_breaks_deadline_arrival_then_id():
    a = request('REQ-0007', 7)
    b = request('REQ-0006', 6)
    c = request('REQ-0001', 6)
    for r in (a,b,c):
        r['priority_score'] = 50.0
    assert sorted([a,b,c],key=priority_key) == [c,b,a]
    a['deadline']='2026-11-09'
    assert sorted([a,b,c],key=priority_key)[0] == a


def test_waiting_caps_at_100():
    r = request('REQ-0001',1,'Graduating','2026-10-01','2026-09-01')
    assert calculate_score(r,date(2026,11,10)) == 100.0


def test_live_submission_updates_all_three_adts():
    engine=QueueEngine([])
    first=request('REQ-0001',1)
    engine.add_record(first)
    assert engine.arrivals.traverse()==['REQ-0001']
    assert engine.hash_table.get('REQ-0001') is first
    assert engine.heap.peek()=='REQ-0001'
    assert engine.heap.valid()
    with pytest.raises(ValueError):
        engine.add_record(first)
    with pytest.raises(ValueError):
        engine.add_record(request('REQ-0002',1))
    assert len(engine.records)==1
