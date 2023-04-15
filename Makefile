
# Redirect to GNU make

.SUFFIXES:

default: config/finished
	"$$(cat config/config.var/bup-make)"

.DEFAULT:
	$(MAKE) config/finished
	"$$(cat config/config.var/bup-make)" $(.TARGETS)

# Dependency changes here should be mirrored in GNUmakefile
config/finished: configure config/configure config/configure.inc config/*.in
	MAKE= ./configure
