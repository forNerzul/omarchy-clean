PYTHON ?= python3
PREFIX ?= /usr/local
DESTDIR ?=
LIBDIR = $(PREFIX)/lib/omarchy-clean
POLKITDIR ?= /usr/share/polkit-1/actions

.PHONY: test check install uninstall

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -t . -v

check: test
	bash -n install.sh uninstall.sh bin/omarchy-clean-setup

install:
	install -d -m 755 $(DESTDIR)$(LIBDIR)/src/omarchy_clean $(DESTDIR)$(LIBDIR)/bin
	install -m 644 src/omarchy_clean/*.py $(DESTDIR)$(LIBDIR)/src/omarchy_clean/
	install -m 755 bin/omarchy-clean bin/omarchy-clean-helper $(DESTDIR)$(LIBDIR)/bin/
	install -d -m 755 $(DESTDIR)$(PREFIX)/bin
	ln -sf ../lib/omarchy-clean/bin/omarchy-clean $(DESTDIR)$(PREFIX)/bin/omarchy-clean
	install -Dm 755 bin/omarchy-clean-setup $(DESTDIR)$(PREFIX)/bin/omarchy-clean-setup
	install -Dm 644 packaging/omarchy-clean.desktop $(DESTDIR)$(PREFIX)/share/applications/omarchy-clean.desktop
	install -d -m 755 $(DESTDIR)$(POLKITDIR)
	sed 's|@HELPER_PATH@|$(LIBDIR)/bin/omarchy-clean-helper|' \
		packaging/dev.omarchy.clean.policy.in > $(DESTDIR)$(POLKITDIR)/dev.omarchy.clean.policy
	chmod 644 $(DESTDIR)$(POLKITDIR)/dev.omarchy.clean.policy

uninstall:
	rm -rf $(DESTDIR)$(LIBDIR)
	rm -f $(DESTDIR)$(PREFIX)/bin/omarchy-clean $(DESTDIR)$(PREFIX)/bin/omarchy-clean-setup \
		$(DESTDIR)$(PREFIX)/share/applications/omarchy-clean.desktop \
		$(DESTDIR)$(POLKITDIR)/dev.omarchy.clean.policy
