% bup-ls(1) Bup %BUP_VERSION%
% Johannes Berg <johannes@sipsolutions.net>
% %BUP_DATE%

# NAME

bup-genkey - generate keys for an encrypted repo

# SYNOPSIS

bup genkey

# DESCRIPTION

`bup genkey` generates keys for creating an encrypted repository.

For writing to a repository, the `readkey` isn't necessary and can
be removed from the configuration, in this case the writing system
can continue making (deduplicated) backups, but cannot read back
any of the old data.

The `writekey` can be derived from the `readkey`, and thus need not
be present in the configuration file if `readkey` is present.

Keys are generated randomly and there's no way to influence this.

# BUP

Part of the `bup`(1) suite.
