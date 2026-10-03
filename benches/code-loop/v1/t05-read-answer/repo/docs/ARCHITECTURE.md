# pulsegate architecture

pulsegate is a webhook relay: it accepts events from producers, queues them,
and delivers them to a single upstream ingest endpoint.

## Pipeline

    producer --(CLI `send` / HTTP POST /events)--> intake --> Relay queue
                                                                  |
                                                     worker `drain` --> upstream

1. **Intake.** Two front doors exist: the command line (`pulsegate/cli.py`)
   and the HTTP server (`pulsegate/web.py`). Both are thin. They turn their
   transport's representation of the payload into a dict and pass it to the
   shared intake code in `pulsegate/core.py`, which validates it, mints the
   event id and pushes the record onto the relay queue.
2. **Queue.** `Relay` keeps records in memory and mirrors them as JSON files
   under `queue.dir` (see `config.yaml`).
3. **Delivery.** `pulsegate/worker.py` drains the queue through
   `pulsegate/transport.py`. A failed delivery is not dropped: the worker
   consults the retry policy before scheduling another attempt.

## Settings

Values come, in order of precedence, from environment variables, then from
`config.yaml`, then from nothing at all (a missing key is an error). The
mapping between variable names and config keys lives in
`pulsegate/settings.py`; that file is the reference, not this document.

Historical note: 0.2 deployments read `PGATE_PORT` and fell back to port 8080.
Both were retired in 0.3. The port now comes from `config.yaml` unless the
environment overrides it. Some old comments still mention 8080.

## Retries and reconnects

Two unrelated budgets exist and are easy to confuse:

- the *transport* reconnect budget, which only covers opening the TCP
  connection to the upstream host and is consumed inside a single delivery
  attempt;
- the *delivery* retry policy, which decides how many times an event is
  attempted end to end and how long to wait between attempts.

This document used to state the delivery budget as 3 attempts. That figure
dates from 0.2 and is no longer maintained here; the policy module is the
source of truth.
