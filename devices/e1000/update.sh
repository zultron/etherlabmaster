#!/bin/bash

set -x

KERNELDIR=/data/kernel/linux-3.12.26
PREVER=3.10
KERNELVER=3.12

for f in $KERNELDIR/drivers/net/ethernet/intel/e1000/*.[ch]; do
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
    sed -i s/$PREVER-ethercat.h/$KERNELVER-ethercat.h/ $e
    hg add $o $e
done
