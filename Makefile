CFLAGS=-Wall -g -Werror

all: hsplit

hsplit: hsplit.o

hjoin: hjoin.sh

test: hsplit
	./hsplit <testfile1 >tags1
	./hsplit <testfile2 >tags2
	diff -u -U50 tags1 tags2

%: %.o
	gcc -o $@ $< $(LDFLAGS) $(LIBS)
	
%: %.sh
	rm -f $@
	ln -s $^ $@
	
%.o: %.c
	gcc -c -o $@ $^ $(CPPFLAGS) $(CFLAGS)

clean:
	rm -f *.o *~ hsplit hjoin
