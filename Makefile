OS:=$(shell uname | sed 's/[-_].*//')
CFLAGS=-Wall -g -O2 -Werror $(PYINCLUDE) -g
ifneq ($(OS),CYGWIN)
  CFLAGS += -fPIC
endif
SHARED=-shared
SOEXT:=.so

ifeq (${OS},Darwin)
  MACHINE:=$(shell arch)
  CFLAGS += -arch $(MACHINE)
  SHARED = -dynamiclib
endif
ifeq ($(OS),CYGWIN)
  LDFLAGS += -L/usr/bin
  EXT:=.exe
  SOEXT:=.dll
endif

default: all

all: cmds bup lib/bup/_hashsplit$(SOEXT) \
	Documentation/all
	
%/all:
	$(MAKE) -C $* all
	
%/clean:
	$(MAKE) -C $* clean

lib/bup/_hashsplit$(SOEXT): lib/bup/_hashsplit.c lib/bup/csetup.py
	@rm -f $@
	cd lib/bup && python csetup.py build
	cp lib/bup/build/*/_hashsplit$(SOEXT) lib/bup/
	
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
	$(CC) $(CFLAGS) (LDFLAGS) -o $@ $^ $(LIBS)
	
bup: main.py
	rm -f $@
	ln -s $< $@
	
cmds: $(patsubst cmd/%-cmd.py,cmd/bup-%,$(wildcard cmd/*-cmd.py))

cmd/bup-%: cmd/%-cmd.py
	rm -f $@
	ln -s $*-cmd.py $@
	
%: %.py
	rm -f $@
	ln -s $< $@
	
bup-%: cmd-%.sh
	rm -f $@
	ln -s $< $@
	
%.o: %.c
	gcc -c -o $@ $< $(CPPFLAGS) $(CFLAGS)

clean: Documentation/clean
	rm -f *.o *.so */*/*.so *.dll *.exe .*~ *~ */*~ */*/*~ \
		*.pyc */*.pyc */*/*.pyc\
		bup bup-* cmd/bup-* randomgen memtest \
		out[12] out2[tc] tags[12] tags2[tc]
	rm -rf *.tmp build lib/bup/build
