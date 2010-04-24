PANDOC:=$(shell \
	if pandoc </dev/null 2>/dev/null; then \
		echo pandoc; \
	else \
		echo "Warning: pandoc not installed; can't generate manpages." >&2; \
		echo '@echo Skipping: pandoc'; \
	fi)
BUP_VERSION:=$(shell ../bup version --tag)
BUP_DATE:=$(shell ../bup version --date)

default: all

all: man html

man: $(patsubst %.md,%,$(wildcard *.md))

html: $(patsubst %.1.md,%.html,$(wildcard *.md))

%: %.md.tmp Makefile
	$(PANDOC) -s -r markdown -w man -o $@ $<
	
%.html: %.1.md.tmp Makefile
	$(PANDOC) -s -r markdown -w html -o $@ $<
	
.PRECIOUS: %.md.tmp
%.md.tmp: %.md Makefile
	rm -f $@ $@.new
	sed -e 's,%BUP_VERSION%,${BUP_VERSION},g' \
	    -e 's,%BUP_DATE%,${BUP_DATE},g' <$< >$@.new
	mv $@.new $@

clean:
	rm -f *~ .*~ *.[0-9] *.new *.tmp *.html
