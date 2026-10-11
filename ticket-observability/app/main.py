import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import Counter, Gauge, Histogram, Summary, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="ticket booking app")

# our "database" is just python dictionaries in memory
events = {
    1: {"name": "Rock Night", "total_seats": 100, "booked": 0},
    2: {"name": "Comedy Show", "total_seats": 50, "booked": 0},
    3: {"name": "Tech Conference", "total_seats": 200, "booked": 0},
}

bookings = {}
next_booking_id = 1

#   ------------------------------ METRICS ------------------------------ #

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

    if event_id not in events:
        raise HTTPException(status_code=404, detail="event not found")
    if seats < 1:
        raise HTTPException(status_code=400, detail="seats must be at least 1")

    event = events[event_id]
    seats_left = event["total_seats"] - event["booked"]
    if seats > seats_left:
        raise HTTPException(status_code=409, detail="not enough seats left")

    # everything is fine, so we save the booking
    event["booked"] += seats
    booking_id = next_booking_id
    next_booking_id += 1
    bookings[booking_id] = {"event_id": event_id, "seats": seats, "status": "confirmed"}

    tickets_booked_total.labels(event_id=str(event_id)).inc(seats)
    seats_currently_booked.inc(seats)

    return {"booking_id": booking_id, "event": event["name"], "seats": seats, "status": "confirmed"}


@app.post("/cancel/{booking_id}")
def cancel_booking(booking_id: int):
    if booking_id not in bookings:
        raise HTTPException(status_code=404, detail="booking not found")

    booking = bookings[booking_id]
    if booking["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="already cancelled")

    # give the seats back
    events[booking["event_id"]]["booked"] -= booking["seats"]
    booking["status"] = "cancelled"

    bookings_cancelled_total.inc()
    seats_currently_booked.dec(booking["seats"])

    return {"booking_id": booking_id, "status": "cancelled"}