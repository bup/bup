PYINCLUDE:=$(shell python2.5-config --includes)
PYLIB:=$(shell python2.5-config --lib)
OS:=$(shell uname | sed 's/[-_].*//')
MACHINE:=$(shell uname -m)
CFLAGS=-Wall -g -O2 -Werror $(PYINCLUDE) -g
ifneq ($(OS),CYGWIN)
  CFLAGS += -fPIC
endif
SHARED=-shared
SOEXT:=.so

ifeq (${OS},Darwin)
  CFLAGS += -arch $(MACHINE)
  SHARED = -dynamiclib
endif
ifeq ($(OS),CYGWIN)
  LDFLAGS += -L/usr/bin
  EXT:=.exe
  SOEXT:=.dll
endif

default: all

all: bup-split bup-join bup-save bup-init bup-server bup-index bup-tick \
	bup memtest randomgen$(EXT) chashsplit$(SOEXT)

randomgen$(EXT): randomgen.o
	$(CC) $(CFLAGS) -o $@ $<

chashsplit$(SOEXT): chashsplitmodule.o
	$(CC) $(CFLAGS) $(LDFLAGS) $(SHARED) -o $@ $< $(PYLIB)
	
runtests: all runtests-python runtests-cmdline

runtests-python:
	./wvtest.py $(wildcard t/t*.py)
	
runtests-cmdline: all
	t/test.sh
	
stupid:
	PATH=/bin:/usr/bin $(MAKE) test
	
test: all
	./wvtestrun $(MAKE) runtests

%: %.o
	$(CC) $(CFLAGS) (LDFLAGS) -o $@ $< $(LIBS)
	
bup: bup.py
	rm -f $@
	ln -s $^ $@
	
bup-%: cmd-%.py
	rm -f $@
	ln -s $^ $@
	
%: %.py
	rm -f $@
	ln -s $^ $@
	
bup-%: cmd-%.sh
	rm -f $@
	ln -s $^ $@
	
%.o: %.c
	gcc -c -o $@ $^ $(CPPFLAGS) $(CFLAGS)

clean:
	rm -f *.o *.so *.dll *.exe *~ .*~ *.pyc */*.pyc */*~ \
		bup bup-* randomgen \
		out[12] out2[tc] tags[12] tags2[tc]
	rm -rf *.tmp
