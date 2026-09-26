import time
import random
import json
import logging
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import Counter, Gauge, Histogram, Summary, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="ticket booking app")

# chaos flag: when True, /book sleeps briefly to simulate a slow dependency
chaos_delay_enabled = False
chaos_delay_seconds = 0.5

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "time": datetime.utcnow().isoformat(),
            "service_name": "ticket-app",
            "severity": record.levelname,
            "message": record.getMessage(),
        }

        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id

        if hasattr(record, "event_id"):
            log_record["event_id"] = record.event_id

        if hasattr(record, "seats"):
            log_record["seats"] = record.seats

        return json.dumps(log_record)


logger = logging.getLogger("ticket-app")
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())

logger.addHandler(handler)
logger.setLevel(logging.INFO)


# our "database" is just python dictionaries in memory
events = {
    1: {"name": "Rock Night", "total_seats": 100, "booked": 0},
    2: {"name": "Comedy Show", "total_seats": 50, "booked": 0},
    3: {"name": "Tech Conference", "total_seats": 200, "booked": 0},
}

bookings = {}
next_booking_id = 1

# ---- metrics ----

# counter: only ever goes up. counts every request by path, method, and status code
http_requests_total = Counter(
    "http_requests_total",
    "total number of http requests",
    ["method", "path", "status"],
)

# histogram: buckets request time so we can compute p95 / p99 later
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "how long each request took, in seconds",
    ["method", "path"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

# business counters
tickets_booked_total = Counter(
    "tickets_booked_total",
    "total number of tickets booked",
    ["event_id"],
)

bookings_cancelled_total = Counter(
    "bookings_cancelled_total",
    "total number of bookings cancelled",
)

# gauge: goes up and down. tracks how many seats are currently booked across all events
seats_currently_booked = Gauge(
    "seats_currently_booked",
    "total seats currently booked across all events",
)

# summary: reports average booking processing time (python summaries have no percentiles,
# so we use the histogram above for p95/p99)
booking_processing_seconds = Summary(
    "booking_processing_seconds",
    "time taken to process a booking request",
)
# demo counter for the cardinality experiment: request_id as a label is a bad practice,
# this metric exists ONLY to demonstrate why
demo_requests_total = Counter(
    "demo_requests_total",
    "demo counter with high-cardinality request_id label (for cardinality experiment only)",
    ["request_id"],
)

# this middleware runs around every single request, so it's where we record
# the counter and histogram for all endpoints in one place
@app.middleware("http")
async def track_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    path = request.url.path
    if path != "/metrics":  # don't count prometheus scraping itself
        http_requests_total.labels(method=request.method, path=path, status=response.status_code).inc()
        http_request_duration_seconds.labels(method=request.method, path=path).observe(duration)

    return response


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/events")
def list_events():
    result = []
    for event_id in events:
        event = events[event_id]
        seats_left = event["total_seats"] - event["booked"]
        result.append({"event_id": event_id, "name": event["name"], "seats_left": seats_left})
    return result


@app.post("/book")
@booking_processing_seconds.time()
def book_ticket(event_id: int, seats: int = 1):
    global next_booking_id

    request_id = str(uuid.uuid4())
    if cardinality_bomb_enabled:
        demo_requests_total.labels(request_id=request_id).inc()

    # chaos injection: simulate a slow dependency on some requests
    if chaos_delay_enabled and random.random() < 0.2:  # 20% of requests
        time.sleep(chaos_delay_seconds)

    if event_id not in events:
        logger.warning(
            "Booking failed: event not found",
            extra={"event_id": event_id, "seats": seats, "request_id": request_id},
        )
        raise HTTPException(status_code=404, detail="event not found")

    if seats < 1:
        logger.warning(
            "Booking failed: invalid seat count",
            extra={"event_id": event_id, "seats": seats, "request_id": request_id},
        )
        raise HTTPException(status_code=400, detail="seats must be at least 1")

    event = events[event_id]
    seats_left = event["total_seats"] - event["booked"]
    if seats > seats_left:
        logger.warning(
            "Booking failed: not enough seats left",
            extra={"event_id": event_id, "seats": seats, "request_id": request_id},
        )
        raise HTTPException(status_code=409, detail="not enough seats left")

    # everything is fine, so we save the booking
    event["booked"] += seats
    booking_id = next_booking_id
    next_booking_id += 1
    bookings[booking_id] = {"event_id": event_id, "seats": seats, "status": "confirmed"}

    tickets_booked_total.labels(event_id=str(event_id)).inc(seats)
    seats_currently_booked.inc(seats)

    logger.info(
        "Ticket booking successful",
        extra={"event_id": event_id, "seats": seats, "request_id": request_id},
    )

    return {"booking_id": booking_id, "event": event["name"], "seats": seats, "status": "confirmed"}


@app.post("/cancel/{booking_id}")
def cancel_booking(booking_id: int):
    request_id = str(uuid.uuid4())

    if booking_id not in bookings:
        logger.warning(
            "Cancel failed: booking not found",
            extra={"request_id": request_id},
        )
        raise HTTPException(status_code=404, detail="booking not found")

    booking = bookings[booking_id]
    if booking["status"] == "cancelled":
        logger.warning(
            "Cancel failed: already cancelled",
            extra={"event_id": booking["event_id"], "seats": booking["seats"], "request_id": request_id},
        )
        raise HTTPException(status_code=409, detail="already cancelled")

    # give the seats back
    events[booking["event_id"]]["booked"] -= booking["seats"]
    booking["status"] = "cancelled"

    bookings_cancelled_total.inc()
    seats_currently_booked.dec(booking["seats"])

    logger.info(
        "Booking cancelled",
        extra={"event_id": booking["event_id"], "seats": booking["seats"], "request_id": request_id},
    )

    return {"booking_id": booking_id, "status": "cancelled"}

@app.post("/chaos/delay")
def toggle_delay(enabled: bool, delay: float = 0.5):
    global chaos_delay_enabled, chaos_delay_seconds
    chaos_delay_enabled = enabled
    chaos_delay_seconds = delay
    return {"chaos_delay_enabled": chaos_delay_enabled, "delay_seconds": chaos_delay_seconds}

cardinality_bomb_enabled = False

@app.post("/chaos/cardinality")
def toggle_cardinality(enabled: bool):
    global cardinality_bomb_enabled
    cardinality_bomb_enabled = enabled
    return {"cardinality_bomb_enabled": cardinality_bomb_enabled}