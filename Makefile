CFLAGS=-Wall -g -Werror

all: hsplit

hsplit: hsplit.o

hjoin: hjoin.o

%: %.o
	gcc -o $@ $< $(LDFLAGS) $(LIBS)
	
%.o: %.c
	gcc -c -o $@ $^ $(CPPFLAGS) $(CFLAGS)

clean:
	rm -f *.o *~ hsplit hjoin
