PYTHON ?= python3

.PHONY: test check

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -t . -v

check: test
	bash -n install.sh uninstall.sh
