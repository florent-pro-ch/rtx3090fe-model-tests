PY ?= python3

# Host-side port used only by the docker-run target (container side is fixed).
HOST_PORT ?= 8080
IMAGE ?= pulsegate:dev

.PHONY: test serve drain docker-run clean

test:
	$(PY) -m unittest discover -s tests -v

serve:
	$(PY) -m pulsegate.cli serve

drain:
	$(PY) -m pulsegate.cli drain

docker-run:
	docker run --rm -p $(HOST_PORT):9130 $(IMAGE)

clean:
	rm -rf var/queue
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
