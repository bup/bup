-include config.vars

config.h: configure configure.inc $(wildcard *.in)
	./configure

clean:
	rm -f ${CONFIGURE_FILES} ${GENERATED_FILES}
	rm -f *~ .*~
