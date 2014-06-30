#!/usr/bin/env perl
use warnings;
use strict;

sub fix($) {
    my $s = shift;
    chomp $s;
    return $s;
}

sub ex
{
  my ($cmd) = @_;
  my $result = `$cmd` or die 'FAILED: ' . $cmd;
  return $result;
}

while (<>) {
    s{
	\$Format:\%d\$
    }{
	my $tag = fix(ex('git describe --match="[0-9]*"'));
	"(tag: bup-$tag)"
    }ex;
    
    s{ 
	\$Format:([^\$].*)\$
    }{
	fix(ex("git log -1 --pretty=format:'$1'"))
    }ex;
    print;
}
