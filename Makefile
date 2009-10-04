CFLAGS=-Wall -g -Werror

all: hsplit

hsplit: hsplit.o

hjoin: hjoin.sh

test: hsplit hjoin
	./hsplit <testfile1 >tags1
	./hsplit <testfile2 >tags2
	diff -u -U50 tags1 tags2 || true
	wc -c testfile1 testfile2
	wc -l tags1 tags2
	./hjoin <tags1 >out1
	./hjoin <tags2 >out2
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
	rm -f *.o *~ hsplit hjoin
