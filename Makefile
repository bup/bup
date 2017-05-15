
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

bup_cmds := cmd/bup-python\
  $(patsubst cmd/%-cmd.py,cmd/bup-%,$(wildcard cmd/*-cmd.py)) \
  $(patsubst cmd/%-cmd.sh,cmd/bup-%,$(wildcard cmd/*-cmd.sh))

bup_deps := bup lib/bup/_checkout.py lib/bup/_helpers$(SOEXT) $(bup_cmds)

all: $(bup_deps) Documentation/all $(current_sampledata)

bup:
	ln -s main.py bup

$(current_sampledata):
	t/configure-sampledata --setup

define install-python-bin
  set -e; \
  sed -e '1 s|.*|#!$(bup_python)|; 2,/^# end of bup preamble$$/d' $1 > $2; \
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
	$(call install-python-bin,bup,"$(dest_bindir)/bup")
	set -e; \
	for cmd in $$(ls cmd/bup-* | grep -v cmd/bup-python); do \
	  $(call install-python-bin,"$$cmd","$(dest_libdir)/$$cmd") \
	done
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
		config/config.h \
		lib/bup/bupsplit.c lib/bup/_helpers.c lib/bup/csetup.py
	@rm -f $@
	cd lib/bup && \
	LDFLAGS="$(LDFLAGS)" CFLAGS="$(CFLAGS)" "$(bup_python)" csetup.py build
	cp lib/bup/build/*/_helpers$(SOEXT) lib/bup/

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

# The "pwd -P" here may not be appropriate in the long run, but we
# need it until we settle the relevant drecurse/exclusion questions:
# https://groups.google.com/forum/#!topic/bup-list/9ke-Mbp10Q0
runtests-python: all t/tmp
	$(pf); cd $$(pwd -P); TMPDIR="$(test_tmp)" \
	  "$(bup_python)" wvtest.py t/t*.py lib/*/t/t*.py 2>&1 \
	    | tee -a t/tmp/test-log/$$$$.log

cmdline_tests := \
  t/test-packsizelimit \
  t/test-prune-older \
  t/test-web.sh \
  t/test-rm.sh \
  t/test-gc.sh \
  t/test-main.sh \
  t/test-list-idx.sh \
  t/test-index.sh \
  t/test-split-join.sh \
  t/test-fuse.sh \
  t/test-drecurse.sh \
  t/test-cat-file.sh \
  t/test-compression.sh \
  t/test-fsck.sh \
  t/test-index-clear.sh \
  t/test-index-check-device.sh \
  t/test-ls.sh \
  t/test-tz.sh \
  t/test-meta.sh \
  t/test-on.sh \
  t/test-restore-map-owner.sh \
  t/test-restore-single-file.sh \
  t/test-rm-between-index-and-save.sh \
  t/test-save-with-valid-parent.sh \
  t/test-sparse-files.sh \
  t/test-command-without-init-fails.sh \
  t/test-redundant-saves.sh \
  t/test-save-creates-no-unrefs.sh \
  t/test-save-restore-excludes.sh \
  t/test-save-strip-graft.sh \
  t/test-import-duplicity.sh \
  t/test-import-rdiff-backup.sh \
  t/test-xdev.sh \
  t/test.sh

# For parallel runs.
# The "pwd -P" here may not be appropriate in the long run, but we
# need it until we settle the relevant drecurse/exclusion questions:
# https://groups.google.com/forum/#!topic/bup-list/9ke-Mbp10Q0
tmp-target-run-test%: all t/tmp
	$(pf); cd $$(pwd -P); TMPDIR="$(test_tmp)" \
	  t/test$* 2>&1 | tee -a t/tmp/test-log/$$$$.log

runtests-cmdline: $(subst t/test,tmp-target-run-test,$(cmdline_tests))

stupid:
	PATH=/bin:/usr/bin $(MAKE) test

test: all
	if test -e t/tmp/test-log; then rm -r t/tmp/test-log; fi
	mkdir -p t/tmp/test-log
	./wvtest watch --no-counts \
	  $(MAKE) runtests-python runtests-cmdline 2>t/tmp/test-log/$$$$.log
	./wvtest report t/tmp/test-log/*.log

check: test

distcheck: all
	./wvtest run t/test-release-archive.sh

cmd/python-cmd.sh: config/config.vars Makefile
	printf "#!/bin/sh\nexec %q \"\$$@\"" "$(bup_python)" \
	  >> cmd/python-cmd.sh.$$PPID.tmp
	chmod +x cmd/python-cmd.sh.$$PPID.tmp
	mv cmd/python-cmd.sh.$$PPID.tmp cmd/python-cmd.sh

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

# update the local 'man' and 'html' branches with pregenerated output files, for
# people who don't have pandoc (and maybe to aid in google searches or something)
export-docs: Documentation/all
	git update-ref refs/heads/man origin/man '' 2>/dev/null || true
	git update-ref refs/heads/html origin/html '' 2>/dev/null || true
	set -eo pipefail; \
	GIT_INDEX_FILE=gitindex.tmp; export GIT_INDEX_FILE; \
	rm -f $${GIT_INDEX_FILE} && \
	git add -f Documentation/*.1 && \
	git update-ref refs/heads/man \
		$$(echo "Autogenerated man pages for $$(git describe --always)" \
		    | git commit-tree $$(git write-tree --prefix=Documentation) \
				-p refs/heads/man) && \
	rm -f $${GIT_INDEX_FILE} && \
	git add -f Documentation/*.html && \
	git update-ref refs/heads/html \
		$$(echo "Autogenerated html pages for $$(git describe --always)" \
		    | git commit-tree $$(git write-tree --prefix=Documentation) \
				-p refs/heads/html)

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
	rm -f *.o lib/*/*.o *.so lib/*/*.so *.dll lib/*/*.dll *.exe \
		.*~ *~ */*~ lib/*/*~ lib/*/*/*~ \
		*.pyc */*.pyc lib/*/*.pyc lib/*/*/*.pyc \
		bup bup-* \
		randomgen memtest \
		testfs.img lib/bup/t/testfs.img
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
	rm -f cmd/bup-* cmd/python-cmd.sh
