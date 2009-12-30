CFLAGS=-Wall -g -Werror -I/usr/include/python2.5 -g -fwrapv -fPIC

default: all

all: hashsplit hashjoin datagen hashsplit.so

hashsplit: hashsplit.o

datagen: datagen.o

hashjoin: hashjoin.sh

hashsplit.so: hashsplitmodule.o
	$(CC) -shared -Wl,-Bsymbolic-functions -o $@ $<

test: hashsplit hashjoin
	./hashsplit.py <testfile1 >tags1
	./hashsplit.py <testfile2 >tags2
	diff -u tags1 tags2 || true
	wc -c testfile1 testfile2
	wc -l tags1 tags2
	./hashjoin <tags1 >out1
	./hashjoin <tags2 >out2
	diff -u testfile1 out1
	diff -u testfile2 out2

%: %.o
	gcc -o $@ $< $(LDFLAGS) $(LIBS)
	
%: %.sh
	rm -f $@
	ln -s $^ $@
	
%.o: %.c
	gcc -c -o $@ $^ $(CPPFLAGS) $(CFLAGS)

clean:
	rm -f *.o *.so *~ hashsplit hashjoin hsplit hjoin datagen \
		out[12] tags[12] .*~
