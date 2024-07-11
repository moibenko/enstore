#!/bin/bash
# run as enstore/package_enstore_bin.sh from directory above enstore
NAME=enstore_bin_distr
VERSION=0.1
REL=3
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
sed -e "s/__VERSION__/${VERSION}/g" -e "s/__RELEASE__/${REL}/g" ./enstore/spec/enstore_RH7_bin_distr.spec >  ~/rpm/SPECS/enstore_RH7_bin_distr.spec

# Package product for rpmbuild
export ENSTORE_INSTALL_DIR=$HOME/enstore_bin_distr_dir/${VERS}
if [ ! -d $ENSTORE_INSTALL_DIR ]; then
    mkdir -p $ENSTORE_INSTALL_DIR
fi

pushd .
cd enstore/pyinstaller
make clean; make enstore
popd
mkdir -p $ENSTORE_INSTALL_DIR/doc
mkdir -p $ENSTORE_INSTALL_DIR/etc
mkdir -p $ENSTORE_INSTALL_DIR/sbin
mkdir -p $ENSTORE_INSTALL_DIR/bin
cp $ENSTORE_DIR/README $ENSTORE_INSTALL_DIR
cp $ENSTORE_DIR/LICENSE $ENSTORE_INSTALL_DIR
cp $ENSTORE_DIR/doc/*.pdf $ENSTORE_INSTALL_DIR/doc
cp $ENSTORE_DIR/doc/guides/*.pdf $ENSTORE_INSTALL_DIR/doc
cp -r $ENSTORE_DIR/databases $ENSTORE_INSTALL_DIR
cp $ENSTORE_DIR/ftt/etc/mkscsidev.Linux $ENSTORE_INSTALL_DIR/etc
sed -e "s/\/enstore/\/enstore_bin_distr/" enstore/etc/enstore.service >  \
 $ENSTORE_INSTALL_DIR/etc/enstore.service
sed -e "s/\/enstore/\/enstore_bin_distr/" enstore/etc/enstore-monitor.service >  \
 $ENSTORE_INSTALL_DIR/etc/enstore-monitor.service


cp enstore/sbin/rc.local $ENSTORE_INSTALL_DIR/sbin
cp enstore/sbin/EPS $ENSTORE_INSTALL_DIR/bin
cd $ENSTORE_INSTALL_DIR

cd ..
echo "PWD `pwd`"
echo "MAKING ${VERS}.tgz"
tar -czf ${VERS}.tgz ${VERS}
cp ${VERS}.tgz ~/rpm/SOURCES/
echo "Calling rpmbuild"
# Create rpmbuild
rpmbuild -bb ~/rpm/SPECS/enstore_RH7_bin_distr.spec || exit 1
#cp ~/rpm/RPMS/noarch/${VERS}-${REL}.noarch.rpm ./bill-calculator/packaging

# Tag 
#TVER="v${VERSION}-${REL}"  
#cd bill-calculator/
#git tag  -m ${TVER} -a ${TVER}
#git push origin ${TVER}
