PYTHON ?= python3

.PHONY: test

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -t . -v
