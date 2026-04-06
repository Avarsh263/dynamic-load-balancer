# Dynamic Load Balancing in Multiprocessor System

A Python simulation of dynamic load balancing across multiple processors,
with a real-time Plotly Dash dashboard.

## Files
- `engine.py` — Core scheduling engine (Round Robin, Least Loaded, Work Stealing)
- `app.py` — Real-time Plotly Dash dashboard

## How to Run
1. Install dependencies:
pip install -r requirements.txt

2. Start the app:
python app.py

3. Open browser at:
http://127.0.0.1:8050

## Algorithms Implemented.
- **Round Robin** — Distributes tasks cyclically across processors
- **Least Loaded** — Always assigns to the least busy processor
- **Work Stealing** — Idle processors steal tasks from overloaded ones

## OS Concepts Covered
Process Scheduling, CPU Burst, Ready Queue, Task Migration,
Mutual Exclusion, Critical Sections, Multiprocessor Load Balancing
```
