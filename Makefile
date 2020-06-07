
SHELL := bash
.DEFAULT_GOAL := all

# See config/config.vars.in (sets bup_python, among other things)
include config/config.vars

pf := set -o pipefail

define isok
  && echo " ok" || echo " no"
endef

# If ok, strip trailing " ok" and return the output, otherwise, error
define shout
$(if $(subst ok,,$(lastword $(1))),$(error $(2)),$(shell x="$(1)"; echo $${x%???}))
endef

sampledata_rev := $(shell t/configure-sampledata --revision $(isok))
sampledata_rev := \
  $(call shout,$(sampledata_rev),Could not parse sampledata revision)

current_sampledata := t/sampledata/var/rev/v$(sampledata_rev)

os := $(shell ($(pf); uname | sed 's/[-_].*//') $(isok))
os := $(call shout,$(os),Unable to determine OS)

CFLAGS := -Wall -O2 -Werror -Wno-unknown-pragmas $(PYINCLUDE) $(CFLAGS)
CFLAGS := -D_FILE_OFFSET_BITS=64 $(CFLAGS)
SOEXT:=.so

ifeq ($(os),CYGWIN)
  SOEXT:=.dll
endif

ifdef TMPDIR
  test_tmp := $(TMPDIR)
else
  test_tmp := $(CURDIR)/t/tmp
endif

initial_setup := $(shell ./configure-version --update $(isok))
initial_setup := $(call shout,$(initial_setup),Version configuration failed))

config/config.vars: configure config/configure config/configure.inc \
  $(wildcard config/*.in)
	MAKE="$(MAKE)" ./configure

# On some platforms, Python.h and readline.h fight over the
# _XOPEN_SOURCE version, i.e. -Werror crashes on a mismatch, so for
# now, we're just going to let Python's version win.
readline_cflags += $(shell pkg-config readline --cflags)
readline_xopen := $(filter -D_XOPEN_SOURCE=%,$(readline_cflags))
readline_xopen := $(subst -D_XOPEN_SOURCE=,,$(readline_xopen))
ifneq ($(readline_xopen),600)
  $(error "Unexpected pkg-config readline _XOPEN_SOURCE --cflags $(readline_cflags)")
endif
readline_cflags := $(filter-out -D_XOPEN_SOURCE=%,$(readline_cflags))
readline_cflags += $(addprefix -DBUP_RL_EXPECTED_XOPEN_SOURCE=,$(readline_xopen))

CFLAGS += $(readline_cflags)
LDFLAGS += $(shell pkg-config readline --libs)

bup_cmds := cmd/bup-python \
  $(patsubst cmd/%-cmd.py,cmd/bup-%,$(wildcard cmd/*-cmd.py)) \
  $(patsubst cmd/%-cmd.sh,cmd/bup-%,$(wildcard cmd/*-cmd.sh))

bup_deps := lib/bup/_checkout.py lib/bup/_helpers$(SOEXT) $(bup_cmds)

all: $(bup_deps) Documentation/all $(current_sampledata)

$(current_sampledata):
	t/configure-sampledata --setup


bup_libdir="$script_home/../lib"  # bup_libdir will be adjusted during install

define install-bup-python
  set -e; \
  sed -e 's|.*# bup_libdir will be adjusted during install|bup_libdir="$$script_home/.."|' $1 > $2; \
  chmod 0755 $2;
endef

PANDOC ?= $(shell type -p pandoc)

ifeq (,$(PANDOC))
  $(shell echo "Warning: pandoc not found; skipping manpage generation" 1>&2)
  man_md :=
else
  man_md := $(wildcard Documentation/*.md)
endif

man_roff := $(patsubst %.md,%.1,$(man_md))
man_html := $(patsubst %.md,%.html,$(man_md))

INSTALL=install
PREFIX=/usr/local
MANDIR=$(PREFIX)/share/man
DOCDIR=$(PREFIX)/share/doc/bup
BINDIR=$(PREFIX)/bin
LIBDIR=$(PREFIX)/lib/bup

dest_mandir := $(DESTDIR)$(MANDIR)
dest_docdir := $(DESTDIR)$(DOCDIR)
dest_bindir := $(DESTDIR)$(BINDIR)
dest_libdir := $(DESTDIR)$(LIBDIR)

install: all
	$(INSTALL) -d $(dest_bindir) \
		$(dest_libdir)/bup $(dest_libdir)/cmd \
		$(dest_libdir)/web $(dest_libdir)/web/static
	test -z "$(man_roff)" || install -d $(dest_mandir)/man1
	test -z "$(man_roff)" || $(INSTALL) -m 0644 $(man_roff) $(dest_mandir)/man1
	test -z "$(man_html)" || install -d $(dest_docdir)
	test -z "$(man_html)" || $(INSTALL) -m 0644 $(man_html) $(dest_docdir)
	$(INSTALL) -pm 0755 cmd/bup $(dest_libdir)/cmd/
	$(INSTALL) -pm 0755 cmd/bup-* $(dest_libdir)/cmd/
	$(call install-bup-python,cmd/bup-python,"$(dest_libdir)/cmd/bup-python")
	cd "$(dest_bindir)" && \
	  ln -sf "$$($(bup_python) -c 'import os; print(os.path.relpath("$(abspath $(dest_libdir))/cmd/bup"))')"
	set -e; \
	$(INSTALL) -pm 0644 \
		lib/bup/*.py \
		$(dest_libdir)/bup
	$(INSTALL) -pm 0755 \
		lib/bup/*$(SOEXT) \
		$(dest_libdir)/bup
	$(INSTALL) -pm 0644 \
		lib/web/static/* \
		$(dest_libdir)/web/static/
	$(INSTALL) -pm 0644 \
		lib/web/*.html \
		$(dest_libdir)/web/

config/config.h: config/config.vars

lib/bup/_helpers$(SOEXT): \
		config/config.h lib/bup/bupsplit.h \
		lib/bup/bupsplit.c lib/bup/_helpers.c lib/bup/csetup.py
	@rm -f $@
	cd lib/bup && $(bup_python) csetup.py build "$(CFLAGS)" "$(LDFLAGS)"
        # Make sure there's just the one file we expect before we copy it.
	"$(bup_python)" -c \
	  "import glob; assert(len(glob.glob('lib/bup/build/*/_helpers*$(SOEXT)')) == 1)"
	cp lib/bup/build/*/_helpers*$(SOEXT) "$@"

lib/bup/_checkout.py:
	@if grep -F '$Format' lib/bup/_release.py \
	    && ! test -e lib/bup/_checkout.py; then \
	  echo "Something has gone wrong; $@ should already exist."; \
	  echo 'Check "./configure-version --update"'; \
	  false; \
	fi

t/tmp:
	mkdir t/tmp

runtests: runtests-python runtests-cmdline

python_tests := \
  lib/bup/t/tbloom.py \
  lib/bup/t/tclient.py \
  lib/bup/t/tgit.py \
  lib/bup/t/thashsplit.py \
  lib/bup/t/thelpers.py \
  lib/bup/t/tindex.py \
  lib/bup/t/tmetadata.py \
  lib/bup/t/toptions.py \
  lib/bup/t/tresolve.py \
  lib/bup/t/tshquote.py \
  lib/bup/t/tvfs.py \
  lib/bup/t/tvint.py \
  lib/bup/t/txstat.py

# The "pwd -P" here may not be appropriate in the long run, but we
# need it until we settle the relevant drecurse/exclusion questions:
# https://groups.google.com/forum/#!topic/bup-list/9ke-Mbp10Q0
runtests-python: all t/tmp
	mkdir -p t/tmp/test-log
	$(pf); cd $$(pwd -P); TMPDIR="$(test_tmp)" \
	  ./wvtest.py  $(python_tests) 2>&1 \
	    | tee -a t/tmp/test-log/$$$$.log

cmdline_tests := \
  t/test.sh \
  t/test-argv \
  t/test-cat-file.sh \
  t/test-command-without-init-fails.sh \
  t/test-compression.sh \
  t/test-drecurse.sh \
  t/test-fsck.sh \
  t/test-fuse.sh \
  t/test-ftp \
  t/test-gc.sh \
  t/test-import-duplicity.sh \
  t/test-import-rdiff-backup.sh \
  t/test-index.sh \
  t/test-index-check-device.sh \
  t/test-index-clear.sh \
  t/test-list-idx.sh \
  t/test-ls \
  t/test-ls-remote \
  t/test-main.sh \
  t/test-meta.sh \
  t/test-on.sh \
  t/test-packsizelimit \
  t/test-prune-older \
  t/test-redundant-saves.sh \
  t/test-restore-map-owner.sh \
  t/test-restore-single-file.sh \
  t/test-rm.sh \
  t/test-rm-between-index-and-save.sh \
  t/test-save-creates-no-unrefs.sh \
  t/test-save-restore \
  t/test-save-errors \
  t/test-save-restore-excludes.sh \
  t/test-save-strip-graft.sh \
  t/test-save-with-valid-parent.sh \
  t/test-sparse-files.sh \
  t/test-split-join.sh \
  t/test-tz.sh \
  t/test-xdev.sh

ifeq "2" "$(bup_python_majver)"
  # unresolved
  #   web: needs more careful attention, path bytes round-trips, reprs, etc.
  cmdline_tests += \
    t/test-web.sh
endif

tmp-target-run-test-get-%: all t/tmp
	$(pf); cd $$(pwd -P); TMPDIR="$(test_tmp)" \
	  t/test-get $* 2>&1 | tee -a t/tmp/test-log/$$$$.log

test_get_targets += \
  tmp-target-run-test-get-replace \
  tmp-target-run-test-get-universal \
  tmp-target-run-test-get-ff \
  tmp-target-run-test-get-append \
  tmp-target-run-test-get-pick \
  tmp-target-run-test-get-new-tag \
  tmp-target-run-test-get-unnamed

# For parallel runs.
# The "pwd -P" here may not be appropriate in the long run, but we
# need it until we settle the relevant drecurse/exclusion questions:
# https://groups.google.com/forum/#!topic/bup-list/9ke-Mbp10Q0
tmp-target-run-test%: all t/tmp
	$(pf); cd $$(pwd -P); TMPDIR="$(test_tmp)" \
	  t/test$* 2>&1 | tee -a t/tmp/test-log/$$$$.log

runtests-cmdline: $(test_get_targets) $(subst t/test,tmp-target-run-test,$(cmdline_tests))

stupid:
	PATH=/bin:/usr/bin $(MAKE) test

test: all
	if test -e t/tmp/test-log; then rm -r t/tmp/test-log; fi
	mkdir -p t/tmp/test-log
	./wvtest watch --no-counts \
	  $(MAKE) runtests 2>t/tmp/test-log/$$$$.log
	./wvtest report t/tmp/test-log/*.log

check: test

distcheck: all
	./wvtest run t/test-release-archive.sh

cmd/bup-python: cmd/python-cmd.sh config/config.var/bup-python
	"$$(cat config/config.var/bup-python)" dev/replace -l '@bup_python@' \
	  "$$(dev/shquote < config/config.var/bup-python)" \
	  < "$<" > "$@".$$PPID.tmp
	chmod +x "$@".$$PPID.tmp
	mv "$@".$$PPID.tmp "$@"

long-test: export BUP_TEST_LEVEL=11
long-test: test

long-check: export BUP_TEST_LEVEL=11
long-check: check

.PHONY: check-both
check-both:
	$(MAKE) clean \
	  && PYTHON=python3 BUP_ALLOW_UNEXPECTED_PYTHON_VERSION=true $(MAKE) check
	$(MAKE) clean \
	  && PYTHON=python2 $(MAKE) check

cmd/bup-%: cmd/%-cmd.py
	rm -f $@
	ln -s $*-cmd.py $@

cmd/bup-%: cmd/%-cmd.sh
	rm -f $@
	ln -s $*-cmd.sh $@

.PHONY: Documentation/all
Documentation/all: $(man_roff) $(man_html)

Documentation/substvars: $(bup_deps)
	echo "s,%BUP_VERSION%,$$(./bup version --tag),g" > $@
	echo "s,%BUP_DATE%,$$(./bup version --date),g" >> $@

Documentation/%.1: Documentation/%.md Documentation/substvars
	$(pf); sed -f Documentation/substvars $< \
	  | $(PANDOC) -s -r markdown -w man -o $@

Documentation/%.html: Documentation/%.md Documentation/substvars
	$(pf); sed -f Documentation/substvars $< \
	  | $(PANDOC) -s -r markdown -w html -o $@

.PHONY: Documentation/clean
Documentation/clean:
	cd Documentation && rm -f *~ .*~ *.[0-9] *.html substvars

# Note: this adds commits containing the current manpages in roff and
# html format to the man and html branches respectively.  The version
# is determined by "git describe --always".
.PHONY: update-doc-branches
update-doc-branches: Documentation/all
	dev/update-doc-branches refs/heads/man refs/heads/html

# push the pregenerated doc files to origin/man and origin/html
push-docs: export-docs
	git push origin man html

# import pregenerated doc files from origin/man and origin/html, in case you
# don't have pandoc but still want to be able to install the docs.
import-docs: Documentation/clean
	$(pf); git archive origin/html | (cd Documentation && tar -xvf -)
	$(pf); git archive origin/man | (cd Documentation && tar -xvf -)

clean: Documentation/clean cmd/bup-python
	cd config && rm -f *~ .*~ \
	  ${CONFIGURE_DETRITUS} ${CONFIGURE_FILES} ${GENERATED_FILES}
	cd config && rm -rf config.var
	rm -f *.o lib/*/*.o *.so lib/*/*.so *.dll lib/*/*.dll *.exe \
		.*~ *~ */*~ lib/*/*~ lib/*/*/*~ \
		*.pyc */*.pyc lib/*/*.pyc lib/*/*/*.pyc \
		randomgen memtest \
		testfs.img lib/bup/t/testfs.img
	for x in $$(ls cmd/*-cmd.py cmd/*-cmd.sh | grep -vF python-cmd.sh | cut -b 5-); do \
	    echo "cmd/bup-$${x%-cmd.*}"; \
	done | xargs -t rm -f
	if test -e t/mnt; then t/cleanup-mounts-under t/mnt; fi
	if test -e t/mnt; then rm -r t/mnt; fi
	if test -e t/tmp; then t/cleanup-mounts-under t/tmp; fi
        # FIXME: migrate these to t/mnt/
	if test -e lib/bup/t/testfs; \
	  then umount lib/bup/t/testfs || true; fi
	rm -rf *.tmp *.tmp.meta t/*.tmp lib/*/*/*.tmp build lib/bup/build lib/bup/t/testfs
	if test -e t/tmp; then t/force-delete t/tmp; fi
	./configure-version --clean
	t/configure-sampledata --clean
        # Remove last so that cleanup tools can depend on it
	rm -f cmd/bup-python
