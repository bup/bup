#!/usr/bin/env perl
use warnings;
use strict;

sub fix($) {
    my $s = shift;
    chomp $s;
    return $s;
}

while (<>) {
    s{
	\$Format:\%d\$
    }{
	my $tag = fix(`git describe --match="[0-9]*"`);
	"(tag: bup-$tag)"
    }ex;
    
    s{ 
	\$Format:([^\$].*)\$
    }{
	fix(`git log -1 --pretty=format:"$1"`)
    }ex;
    print;
}
