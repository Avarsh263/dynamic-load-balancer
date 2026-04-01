"""
Dynamic Load Balancer - Core Engine
=====================================
Real engine implementing three scheduling algorithms.
Drop-in replacement for MockEngine in app.py.

Usage in app.py:
    from engine import Engine
    engine = Engine(num_processors=4)
"""

import threading
import time
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from typing import List, Optional


# ─────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────

@dataclass
class Task:
    """Represents a unit of work to be scheduled."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    duration: float = 0.0        # simulated CPU-seconds needed
    remaining: float = 0.0       # how much work is left
    priority: int = 1            # 1=normal, 2=high
    assigned_to: int = -1        # processor index (-1 = unassigned)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.duration == 0.0:
            self.duration = random.uniform(1.0, 8.0)
        self.remaining = self.duration


@dataclass
class Processor:
    """Represents a single CPU core."""
    proc_id: int
    speed: float = 1.0           # relative processing speed (1.0 = normal)

    # Live state (updated each tick)
    cpu_load: float = 0.0        # 0–100 %
    task_queue: List[Task] = field(default_factory=list)
    completed: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def queue_depth(self) -> int:
        return len(self.task_queue)

    @property
    def total_remaining_work(self) -> float:
        return sum(t.remaining for t in self.task_queue)

    def tick(self, dt: float):
        """
        Advance this processor by dt seconds.
        Processes the front task; updates cpu_load.
        """
        with self.lock:
            if self.task_queue:
                active = self.task_queue[0]
                work_done = dt * self.speed
                active.remaining -= work_done

                if active.remaining <= 0:
                    self.task_queue.pop(0)
                    self.completed += 1

                # Load proportional to queue + remaining work, capped at 98%
                base = min(98, 20 + self.total_remaining_work * 6)
                noise = random.gauss(0, 1.5)
                self.cpu_load = max(2, min(98, base + noise))
            else:
                # Idle drift toward 5%
                self.cpu_load = max(2, self.cpu_load * 0.85 + random.gauss(3, 1))


# ─────────────────────────────────────────────
# ALGORITHMS
# ─────────────────────────────────────────────

class RoundRobin:
    """Distributes tasks cyclically across all processors."""
    def __init__(self, num_processors):
        self._counter = 0
        self._n = num_processors

    def assign(self, task: Task, processors: List[Processor]) -> int:
        target = self._counter % self._n
        self._counter += 1
        return target

    def rebalance(self, processors: List[Processor]):
        pass  # Round Robin doesn't rebalance after assignment


class LeastLoaded:
    """Always assigns new tasks to the processor with the lowest current load."""

    def assign(self, task: Task, processors: List[Processor]) -> int:
        return min(range(len(processors)), key=lambda i: processors[i].cpu_load)

    def rebalance(self, processors: List[Processor]):
        pass  # Assignment handles balance; no migration needed


class WorkStealing:
    """
    Tasks are assigned to the least loaded processor.
    Additionally, idle processors 'steal' tasks from overloaded ones.
    This is the most adaptive algorithm.
    """
    OVERLOAD_THRESHOLD = 70.0   # % load considered overloaded
    IDLE_THRESHOLD = 20.0       # % load considered idle
    STEAL_RATIO = 0.4           # fraction of victim's queue to steal

    def assign(self, task: Task, processors: List[Processor]) -> int:
        return min(range(len(processors)), key=lambda i: processors[i].cpu_load)

    def rebalance(self, processors: List[Processor]) -> int:
        """
        Returns number of migrations performed this tick.
        Called by the engine after every tick.
        """
        migrations = 0
        overloaded = [p for p in processors if p.cpu_load > self.OVERLOAD_THRESHOLD and p.queue_depth > 1]
        idle = [p for p in processors if p.cpu_load < self.IDLE_THRESHOLD]

        for thief in idle:
            if not overloaded:
                break
            victim = max(overloaded, key=lambda p: p.cpu_load)

            # Steal a slice of victim's queue (skip the active front task)
            with victim.lock, thief.lock:
                stealable = victim.task_queue[1:]  # leave the active task
                n_steal = max(1, int(len(stealable) * self.STEAL_RATIO))
                stolen = stealable[:n_steal]
                victim.task_queue = [victim.task_queue[0]] + stealable[n_steal:]

                for t in stolen:
                    t.assigned_to = thief.proc_id
                thief.task_queue.extend(stolen)
                migrations += len(stolen)

            if victim.queue_depth <= 1:
                overloaded.remove(victim)

        return migrations


# ─────────────────────────────────────────────
# ENGINE
# ─────────────────────────────────────────────

ALGORITHM_MAP = {
    "Round Robin": RoundRobin,
    "Least Loaded": LeastLoaded,
    "Work Stealing": WorkStealing,
}

class Engine:
    """
    Core load balancing engine.

    Runs a background thread that ticks all processors every TICK_INTERVAL
    seconds. Thread-safe state access via get_state().

    Public API (matches MockEngine):
        engine.get_state()          -> dict
        engine.inject_task(n)       -> None
        engine.set_algorithm(name)  -> None
    """

    TICK_INTERVAL = 0.5   # seconds between simulation ticks

    def __init__(self, num_processors: int = 4, algorithm: str = "Round Robin"):
        self.processors = [
            Processor(proc_id=i, speed=random.uniform(0.8, 1.2))
            for i in range(num_processors)
        ]
        self._algorithm_name = algorithm
        self._algorithm = self._make_algorithm(algorithm)
        self._total_injected = 0
        self._migrations = 0
        self._lock = threading.Lock()
        self._event_log: deque = deque(maxlen=50)

        # Seed with some initial tasks so the dashboard isn't empty
        for _ in range(num_processors * 3):
            self._dispatch_task(Task())

        # Start background tick thread
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    # ── Public API ──────────────────────────────

    def get_state(self) -> dict:
        """Return a snapshot of current engine state (thread-safe)."""
        with self._lock:
            loads = [round(p.cpu_load, 1) for p in self.processors]
            queues = [p.queue_depth for p in self.processors]
            completed = sum(p.completed for p in self.processors)

        return {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "loads": loads,
            "queues": queues,
            "algorithm": self._algorithm_name,
            "completed": completed,
            "total_tasks": self._total_injected,
            "migrations": self._migrations,
        }

    def inject_task(self, burst_size: int = 10):
        """Inject a burst of tasks. Called from the dashboard 'Inject' button."""
        tasks = [Task(priority=random.choice([1, 1, 2])) for _ in range(burst_size)]
        with self._lock:
            for task in tasks:
                self._dispatch_task(task)
            self._total_injected += burst_size
        self._log(f"Burst of {burst_size} tasks injected")

    def set_algorithm(self, name: str):
        """Switch balancing algorithm live, without restarting."""
        if name not in ALGORITHM_MAP or name == self._algorithm_name:
            return
        with self._lock:
            self._algorithm_name = name
            self._algorithm = self._make_algorithm(name)
        self._log(f"Algorithm switched to {name}")

    def stop(self):
        """Gracefully stop the background thread."""
        self._running = False
        self._thread.join(timeout=2)

    # ── Internal ────────────────────────────────

    def _make_algorithm(self, name: str):
        cls = ALGORITHM_MAP[name]
        if name == "Round Robin":
            return cls(len(self.processors))
        return cls()

    def _dispatch_task(self, task: Task):
        """Assign a task to a processor using the current algorithm."""
        target_idx = self._algorithm.assign(task, self.processors)
        task.assigned_to = target_idx
        self.processors[target_idx].task_queue.append(task)
        self._total_injected += 1

    def _run_loop(self):
        """Background thread: tick processors and rebalance."""
        while self._running:
            with self._lock:
                for p in self.processors:
                    p.tick(self.TICK_INTERVAL)

                migrations = self._algorithm.rebalance(self.processors)
                if migrations:
                    self._migrations += migrations
                    self._log(f"{migrations} task(s) migrated by {self._algorithm_name}")

                # Occasionally generate background tasks to keep things busy
                if random.random() < 0.3:
                    self._dispatch_task(Task())

            time.sleep(self.TICK_INTERVAL)

    def _log(self, message: str):
        self._event_log.appendleft(
            f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        )