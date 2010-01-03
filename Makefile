CFLAGS=-Wall -g -O2 -Werror -I/usr/include/python2.5 -g -fPIC

default: all

all: bup-split bup-join bup-save bup randomgen chashsplit.so

randomgen: randomgen.o

chashsplit.so: chashsplitmodule.o
	$(CC) -shared -o $@ $<
	
runtests: all
	./wvtest.py $(wildcard t/t*.py)
	
runtests-cmdline: all
	@echo "Testing \"$@\" in Makefile:"
	./bup split --bench -b <testfile1 >tags1.tmp
	./bup split -vvvv -b testfile2 >tags2.tmp
	./bup split -t testfile2 >tags2t.tmp
	./bup split -c testfile2 >tags2c.tmp
	diff -u tags1.tmp tags2.tmp || true
	wc -c testfile1 testfile2
	wc -l tags1.tmp tags2.tmp
	./bup join $$(cat tags1.tmp) >out1.tmp
	./bup join <tags2.tmp >out2.tmp
	./bup join <tags2t.tmp >out2t.tmp
	./bup join <tags2c.tmp >out2c.tmp
	diff -u testfile1 out1.tmp
	diff -u testfile2 out2.tmp
	diff -u testfile2 out2t.tmp
	diff -u testfile2 out2c.tmp
	
test: all runtests-cmdline
	./wvtestrun $(MAKE) runtests

%: %.o
	gcc -o $@ $< $(LDFLAGS) $(LIBS)
	
bup: bup.py
	rm -f $@
	ln -s $^ $@
	
bup-%: cmd-%.py
	rm -f $@
	ln -s $^ $@
	
bup-%: cmd-%.sh
	rm -f $@
	ln -s $^ $@
	
%.o: %.c
	gcc -c -o $@ $^ $(CPPFLAGS) $(CFLAGS)

clean:
	rm -f *.o *.so *~ .*~ *.pyc */*.pyc */*~ \
		bup bup-split bup-join bup-save randomgen \
		out[12] out2[tc] tags[12] tags2[tc] *.tmp
