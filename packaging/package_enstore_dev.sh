#!/bin/bash -x
# run as enstore/package_enstore_dev.sh from directory above enstore
if [ "${1:-}" = "-x" ] ; then set -xv; shift; fi
if [[ ! -v NAME ]]; then
    NAME=enstore_dev
fi
if [[ ! -v VERSION ]]; then
    VERSION=0.0
fi
if [[ ! -v REL ]]; then
    REL=1
fi
VERS=${NAME}-${VERSION}

if [ ! -d enstore ]; then
   echo "`basename $0` is expecting to be executed as enstore/packaging/`basename $0`" >&2
   exit 1
fi

# Create rpm build environment
echo "%_topdir ${HOME}/rpm" > ~/.rpmmacros
echo "%_tmppath /tmp" >> ~/.rpmmacros
#rm -rf ~/rpm
mkdir -p ~/rpm/BUILD ~/rpm/RPMS ~/rpm/SOURCES ~/rpm/SPECS ~/rpm/SRPMS
sed -e "s/__VERSION__/${VERSION}/g" -e "s/__RELEASE__/${REL}/g" -e "s/__NAME__/${NAME}/g" ./enstore/spec/enstore_dev.spec >  ~/rpm/SPECS/enstore_dev.spec

# Package product for rpmbuild
export ENSTORE_INSTALL_DIR=$HOME/enstore_dev/${VERS}
if [ ! -d $ENSTORE_INSTALL_DIR ]; then
    mkdir -p $ENSTORE_INSTALL_DIR
fi

PYTHON_SRC=`pyenv virtualenv-prefix`
if [ -z "${PYTHON_SRC:-}" ]; then
    echo "No python distro found"
    exit 1
fi
cp -r enstore/* $ENSTORE_INSTALL_DIR/
# Remove symlinks if any
find $ENSTORE_INSTALL_DIR -type l -exec rm -f {} \;
mkdir -p $ENSTORE_INSTALL_DIR/Python
cp -r $PYTHON_SRC/* $ENSTORE_INSTALL_DIR/Python

cd $ENSTORE_INSTALL_DIR
export ENSTORE_DIR=$ENSTORE_INSTALL_DIR/
export PYTHON_DIR=$ENSTORE_DIR/Python
export PYTHONINC=`ls -d $PYTHON_DIR/include/python*`
export PYTHONLIB=`ls -d $PYTHON_DIR/lib/python*`
export FTT_DIR=$ENSTORE_DIR/ftt
p=`rpm -ql swig | grep python | head -1`
export SWIG_LIB=`dirname $p`
PYTHONPATH=$PATH:$ENSTORE_DIR:$ENSTORE_DIR/src:$ENSTORE_DIR/modules:$ENSTORE_DIR/HTMLgen:$ENSTORE_DIR/PyGreSQL; export PYTHONPATH
PATH=$PYTHON_DIR/bin:$PYTHONINC:$PATH:$ENSTORE_DIR/sbin:$ENSTORE_DIR/bin:$ENSTORE_DIR/tools:$ENSTORE_DIR/HTMLgen; export PATH
# Copy cgi scripts tp correct location
mkdir -p www/cgi-bin
cp src/*cgi* www/cgi-bin
pushd .
cd ftt/ftt_lib
make clean; make;make install
cd ../../modules
make clean; make
popd
cd ..
echo "MAKING ${VERS}.tgz from `pwd`/${VERS}"
tar -czf ${VERS}.tgz ${VERS} # this works
#tar czvf ${VERS}.tgz . --exclude VERS}.tgz --exclude-vcs
#tar -czf ${VERS}.tgz .
cp ${VERS}.tgz ~/rpm/SOURCES/
echo "PWD `pwd`"
#cp spec/enstore_distr.spec ~/rpm/SPECS
echo "Calling rpmbuild"
# Create rpmbuild
rpmbuild -bb ~/rpm/SPECS/enstore_dev.spec || exit 1

