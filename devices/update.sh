#!/bin/bash

set -x

KERNELDIR=/data/kernel/linux-3.6.11
PREVER=3.4
KERNELVER=3.6

for f in $KERNELDIR/drivers/net/ethernet/realtek/{8139too,r8169}.c; do
    echo $f
    b=$(basename $f)
    o=${b/\./-$KERNELVER-orig.}
    e=${b/\./-$KERNELVER-ethercat.}
    cp -v $f $o
    chmod 644 $o
    cp -v $o $e
    op=${b/\./-$PREVER-orig.}
    ep=${b/\./-$PREVER-ethercat.}
    diff -u $op $ep | patch -p1 $e
done
