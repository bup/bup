
# Technically we need 4.1.90 for .SHELLSTATUS, but everything relevant
# seems to have at least 4.2 (mostly 4.4 and higher) anyway, so let's
# just require 4.2+ to simplify, and if we ever raise the limit to
# 4.4+, we'll have intcmp.

# Assumes make versions always have at least two components.
make_maj := $(word 1,$(subst ., ,$(MAKE_VERSION)))
ifneq (,$(filter $(make_maj),0 1 2 3))
  $(error $(MAKE) version $(MAKE_VERSION) is < 4.2)
endif
make_min := $(word 2,$(subst ., ,$(MAKE_VERSION)))
ifeq (4,$(make_maj))
  ifneq (,$(filter $(make_min),0 1))
    $(error $(MAKE) version $(MAKE_VERSION) is < 4.2)
  endif
endif

.SUFFIXES:
.DELETE_ON_ERROR:

$(shell mkdir -p config/config.var && echo "$(MAKE)" > config/config.var/make)
ifneq (0, $(.SHELLSTATUS))
  $(error Unable to record config/config.var/make)
endif

MAKEFLAGS += --warn-undefined-variables

SHELL := bash
.DEFAULT_GOAL := all

# So where possible we can make tests more reproducible
export BUP_TEST_RANDOM_SEED ?= $(shell echo "$$RANDOM")

# Guard against accidentally using/testing a local bup
export PATH := $(CURDIR)/dev/shadow-bin:$(PATH)

clean_paths :=
doc_clean_paths :=
generated_dependencies :=

# Suppress config.vars undefined variable warnings during initial
# setup.
$(shell test -e config/config.vars)
ifneq (0, $(.SHELLSTATUS))
  bup_config_cflags ?=
  bup_config_ldflags_so ?=
  bup_have_acls ?=
  bup_python_ldflags ?=
  bup_python_ldflags_embed ?=
  bup_readline_cflags ?=
  bup_readline_ldflags ?=
endif

# See ./configure (sets bup_python_config, among other things) and
# produces config.vars, the "configuration succeeded" state file.
include config/config.vars

pf := set -o pipefail

sampledata_rev := $(shell dev/configure-sampledata --revision)
ifneq (0, $(.SHELLSTATUS))
  $(error Could not parse sampledata revision)
endif
current_sampledata := test/sampledata/var/rev/v$(sampledata_rev)

os := $(shell ($(pf); uname | sed 's/[-_].*//'))
ifneq (0, $(.SHELLSTATUS))
  $(error Unable to determine OS)
endif

# CFLAGS CPPFLAGS LDFLAGS are handled vis configure -> config/config.vars

# Satisfy --warn-undefined-variables
DESTDIR ?=
TARGET_ARCH ?=

bup_common_cflags := $(bup_config_cflags)
bup_common_cflags += -O2 -Wall -Werror -Wformat=2 -MMD -MP
bup_common_cflags += -Wno-unknown-pragmas -Wsign-compare
bup_common_cflags += -D_FILE_OFFSET_BITS=64

bup_common_ldflags :=

soext := .so
ifeq ($(os),CYGWIN)
  soext := .dll
endif

ifdef TMPDIR
  test_tmp := $(TMPDIR)
else
  test_tmp := $(CURDIR)/test/tmp
endif

$(shell dev/update-checkout-info lib/bup/checkout_info.py)
ifneq (0, $(.SHELLSTATUS))
  $(error update-checkout-info failed)
endif
clean_paths += lib/bup/checkout_info.py

config/config.vars: configure config/test/*.c
	MAKE="$(MAKE)" ./configure

# On some platforms, Python.h and readline.h fight over the
# _XOPEN_SOURCE version, i.e. -Werror crashes on a mismatch, so for
# now, we're just going to let Python's version win.

helpers_cflags = $(bup_python_cflags) $(bup_common_cflags) -I$(CURDIR)/src
helpers_ldflags := $(bup_python_ldflags) $(bup_common_ldflags)
helpers_ldflags += $(bup_config_ldflags_so)

ifneq ($(strip $(bup_readline_cflags)),)
  readline_cflags += $(bup_readline_cflags)
  readline_xopen := $(filter -D_XOPEN_SOURCE=%,$(readline_cflags))
  readline_xopen := $(subst -D_XOPEN_SOURCE=,,$(readline_xopen))
  readline_cflags := $(filter-out -D_XOPEN_SOURCE=%,$(readline_cflags))
  readline_cflags += $(addprefix -DBUP_RL_EXPECTED_XOPEN_SOURCE=,$(readline_xopen))
  helpers_cflags += $(readline_cflags)
endif

helpers_ldflags += $(bup_readline_ldflags)

ifeq ($(bup_have_acls),1)
  helpers_cflags += $(bup_libacl_cflags)
  helpers_ldflags += $(bup_libacl_ldflags)
endif

bup_ext_cmds := lib/cmd/bup-import-rdiff-backup lib/cmd/bup-import-rsnapshot

bup_deps := lib/bup/_helpers$(soext) lib/cmd/bup

incomplete_saves_svg := \
  issue/missing-objects-fig-bloom-get.svg \
  issue/missing-objects-fig-bloom-set.svg \
  issue/missing-objects-fig-bup-model-2.svg \
  issue/missing-objects-fig-bup-model.svg \
  issue/missing-objects-fig-gc-dangling.svg \
  issue/missing-objects-fig-get-bug-save.svg \
  issue/missing-objects-fig-git-model.svg \
  issue/missing-objects-fig-rm-after-gc.svg \
  issue/missing-objects-fig-rm-after.svg \
  issue/missing-objects-fig-rm-before.svg
clean_paths += $(incomplete_saves_svg)

issue/missing-objects.html: $(incomplete_saves_svg)
clean_paths += issue/missing-objects.html

issue/%.svg: issue/%.dot
	$(DOT) -Tsvg $< > $@

issue/%.html: issue/%.md
	$(PANDOC) -s --embed-resources --resource-path issue \
	  -r markdown -w html -o $@ $<

issues :=
man_md := $(wildcard Documentation/*.md)
man_roff := $(man_md:.md=)
man_html := $(man_md:.md=.html)
docs :=

DOT ?= $(shell type -p dot)
PANDOC ?= $(shell type -p pandoc)

ifeq (,$(PANDOC))
  $(info Warning: pandoc not found; skipping generation of related documents)
else
  docs := $(man_roff) $(man_html)
  doc_clean_paths += $(docs)
  ifeq (,$(findstring --embed-resources,$(shell $(PANDOC) --help)))
    $(info Warning: no pandoc --embed-resources; skipping generation of related documents)
  else
    ifeq (,$(DOT))
      $(info Warning: graphviz dot not found; skipping generation of related documents)
    else
      issues += issue/missing-objects.html
    endif
  endif
endif


all: dev/bup-exec dev/bup-python dev/python $(bup_deps) Documentation/all \
  $(issues) $(current_sampledata)

$(current_sampledata):
	dev/configure-sampledata --setup

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
	$(INSTALL) -d \
	  $(dest_bindir) \
	  $(dest_libdir)/bup/cmd\
	  $(dest_libdir)/bup/repo \
	  $(dest_libdir)/cmd \
	  $(dest_libdir)/web/static
  ifneq (,$(docs))
	for f in $(man_roff); do \
	    sec="$${f##*.}"; \
	    $(INSTALL) -d $(dest_mandir)/man"$$sec"; \
	    $(INSTALL) -m 0644 "$$f" $(dest_mandir)/man"$$sec"; \
	done
	install -d $(dest_docdir)
	$(INSTALL) -m 0644 $(man_html) $(dest_docdir)
  endif
	$(INSTALL) -pm 0755 lib/cmd/bup "$(dest_libdir)/cmd/bup"
	$(INSTALL) -pm 0755 $(bup_ext_cmds) "$(dest_libdir)/cmd/"
	cd "$(dest_bindir)" && \
	  ln -sf "$$($(CURDIR)/dev/python -c 'import os; print(os.path.relpath("$(abspath $(dest_libdir))/cmd/bup"))')" \
	    .
	set -e; \
	$(INSTALL) -pm 0644 lib/bup/*.py $(dest_libdir)/bup/
	$(INSTALL) -pm 0644 lib/bup/cmd/*.py $(dest_libdir)/bup/cmd/
	$(INSTALL) -pm 0644 lib/bup/repo/*.py $(dest_libdir)/bup/repo/
	$(INSTALL) -pm 0755 \
		lib/bup/*$(soext) \
		$(dest_libdir)/bup
	$(INSTALL) -pm 0644 \
		lib/web/static/* \
		$(dest_libdir)/web/static/
	$(INSTALL) -pm 0644 \
		lib/web/*.html \
		$(dest_libdir)/web/
	if test -e lib/bup/checkout_info.py; then \
	    $(INSTALL) -pm 0644 lib/bup/checkout_info.py \
	        $(dest_libdir)/bup/source_info.py; \
	else \
	    ! grep -qF '$$Format' lib/bup/source_info.py; \
	    $(INSTALL) -pm 0644 lib/bup/source_info.py $(dest_libdir)/bup/; \
	fi

embed_cflags = -fPIE $(bup_python_cflags_embed) $(bup_common_cflags) -I$(CURDIR)/src
embed_ldflags := -pie $(bup_python_ldflags_embed) $(bup_common_ldflags)

cc_bin = $(CC) $(embed_cflags) $(CPPFLAGS) $(CFLAGS) -c $< -o $@
ld_bin = $(CC) $(LDFLAGS) $^ -o $@ $(embed_ldflags)

# common files to build for the binaries
src/bup/%.o: src/bup/%.c
	$(cc_bin)
clean_paths += src/bup/compat.o src/bup/io.o
generated_dependencies += src/bup/compat.d src/bup/io.d

clean_paths += dev/python-proposed dev/python-proposed.o
generated_dependencies += dev/python-proposed.d
dev/python-proposed.o: dev/python.c
	$(cc_bin)
dev/python-proposed: dev/python-proposed.o src/bup/compat.o src/bup/io.o
	rm -f dev/python
	$(ld_bin)

clean_paths += dev/python
dev/python: dev/python-proposed
	dev/validate-python $@-proposed
	cp -R -p $@-proposed $@

clean_paths += dev/bup-exec
generated_dependencies += dev/bup-exec.d
dev/bup-exec.o: bup_common_cflags += -D BUP_DEV_BUP_EXEC=1
dev/bup-exec.o: lib/cmd/bup.c
	$(cc_bin)
dev/bup-exec: dev/bup-exec.o src/bup/compat.o src/bup/io.o
	$(ld_bin)

clean_paths += dev/bup-python
generated_dependencies += dev/bup-python.d
dev/bup-python.o: bup_common_cflags += -D BUP_DEV_BUP_PYTHON=1
dev/bup-python.o: lib/cmd/bup.c
	$(cc_bin)
dev/bup-python: dev/bup-python.o src/bup/compat.o src/bup/io.o
	$(ld_bin)

clean_paths += lib/cmd/bup
generated_dependencies += lib/cmd/bup.d
lib/cmd/bup.o: lib/cmd/bup.c
	$(cc_bin)
lib/cmd/bup: lib/cmd/bup.o src/bup/compat.o src/bup/io.o
	$(ld_bin)

cc_helpers = $(CC) -fPIC $(helpers_cflags) $(CPPFLAGS) $(CFLAGS) -c $< -o $@
ld_helpers = $(CC) -fPIC $^ -o $@ $(helpers_ldflags) $(LDFLAGS)

lib/bup/%.o: lib/bup/%.c
	$(cc_helpers)
src/bup/pyutil.o: src/bup/pyutil.c
	$(cc_helpers)

clean_paths += lib/bup/_helpers$(soext) lib/bup/_helpers.o
generated_dependencies += lib/bup/_helpers.d src/bup/pyutil.d lib/bup/bupsplit.d lib/bup/_hashsplit.d
lib/bup/_helpers$(soext): lib/bup/_helpers.o src/bup/pyutil.o lib/bup/bupsplit.o lib/bup/_hashsplit.o
	$(ld_helpers)

test/tmp:
	mkdir test/tmp

# MAKEFLAGS must not be in an immediate := assignment
parallel_opt = $(lastword $(filter -j%,$(MAKEFLAGS)))
get_parallel_n = $(patsubst -j%,%,$(parallel_opt))
maybe_specific_n = $(if $(filter -j%,$(parallel_opt)),-n$(get_parallel_n))
xdist_opt = $(if $(filter -j,$(parallel_opt)),-nauto,$(maybe_specific_n))

.PHONY: lint-lib
lint-lib: dev/bup-exec dev/bup-python
	./pylint lib

# unused-wildcard-import: we always "import * from wvpytest"
.PHONY: lint-test
lint-test: dev/bup-exec dev/bup-python
	./pylint -d unused-wildcard-import test/lib test/int

.PHONY: lint
lint: lint-lib lint-test

check: all test/tmp dev/python lint
        # Ensure we can't test the local bup
	! bup version
	test "$$(command -v bup)" = '$(CURDIR)/dev/shadow-bin/bup'
	./bup features
	./pytest $(xdist_opt)

distcheck: all
	./pytest $(xdist_opt) -m release

long-check: export BUP_TEST_LEVEL=11
long-check: check

.PHONY: Documentation/all
Documentation/all: $(docs)

# Don't rebuild the docs unless the content changes, and don't
# recompute the content unless it might have changed.
Documentation/substvars.current: $(bup_deps)
	(set -e; \
	 bup_ver=$$(./bup version); \
	 bup_date=$$(./bup version --date); \
	 echo -e "s,%BUP_VERSION%,$$bup_ver,g\n" \
	         "s,%BUP_DATE%,$$bup_date,g") > $@
Documentation/substvars: Documentation/substvars.current
	@cmp $@ $< || cp $< $@
doc_clean_paths += substvars substvars.current

define render_page
  $(pf); sed -f Documentation/substvars $< \
    | "$(PANDOC)" -s -r markdown -w $(1) -o $(2)
endef

Documentation/%: Documentation/%.md Documentation/substvars
	$(call render_page,man,$@)
Documentation/%.html: Documentation/%.md Documentation/substvars
	$(call render_page,html,$@)

.PHONY: Documentation/clean
Documentation/clean:
	rm -rf $(doc_clean_paths)

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

.PHONY: clean
clean:
	rm -f config/config.vars # resets configuration

        # Clean up the mounts first, so that find, etc. won't crash later
	if test -e test/mnt; then dev/cleanup-mounts-under test/mnt; fi
	if test -e test/mnt; then rm -r test/mnt; fi
	if test -e test/tmp; then dev/cleanup-mounts-under test/tmp; fi
        # FIXME: migrate these to test/mnt/
	if test -e test/int/testfs; \
	  then umount test/int/testfs || true; fi
	rm -rf test/int/testfs test/int/testfs.img testfs.img

	rm -rf $(bup_config_detritus)
	rm -rf $(doc_clean_paths) $(clean_paths) .pytest_cache
	rm -f $(generated_dependencies)
	if test -e test/tmp; then dev/force-delete test/tmp; fi
	find . -name __pycache__ -exec rm -rf {} +
	dev/configure-sampledata --clean

-include $(generated_dependencies)

# legacy

.PHONY: check-py3
check-py3: check
.PHONY: long-test
long-test: long-check
.PHONY: stupid
stupid: check
.PHONY: test
test: check
