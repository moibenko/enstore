#!/bin/bash
# run as enstore/packaging/package_enstore_bin.sh from directory above enstore
NAME=enstore_bin
VERSION=0.0
REL=0
VERS=${NAME}-${VERSION}

if [ ! -d enstore ]; then
   echo 'package_enstore_bin.sh is expecting to be executed as enstore/package_enstore_bin.sh' >&2
   exit 1
fi

# Create rpm build environment
echo "%_topdir ${HOME}/rpm" > ~/.rpmmacros
echo "%_tmppath /tmp" >> ~/.rpmmacros
rm -rf ~/rpm
mkdir -p ~/rpm/BUILD ~/rpm/RPMS ~/rpm/SOURCES ~/rpm/SPECS ~/rpm/SRPMS
sed -e "s/__VERSION__/${VERSION}/g" -e "s/__RELEASE__/${REL}/g" ./enstore/spec/enstore_RH7_bin.spec >  ~/rpm/SPECS/enstore_RH7_bin.spec

# Package product for rpmbuild
export ENSTORE_INSTALL_DIR=$HOME/enstore_bin_dir/${VERS}
if [ ! -d $ENSTORE_INSTALL_DIR ]; then
    mkdir -p $ENSTORE_INSTALL_DIR
fi
mkdir -p $ENSTORE_INSTALL_DIR/doc
mkdir -p $ENSTORE_INSTALL_DIR/etc
cp -p enstore/README $ENSTORE_INSTALL_DIR
cp -p enstore/doc/*.pdf $ENSTORE_INSTALL_DIR/doc
cp -p enstore/doc/guides/*.pdf $ENSTORE_INSTALL_DIR/doc
cp -rp enstore/databases $ENSTORE_INSTALL_DIR

sed -e "s/\/enstore/\/enstore_bin/" enstore/etc/enstore.service >  \
 $ENSTORE_INSTALL_DIR/etc/enstore.service
sed -e "s/\/enstore/\/enstore_bin/" enstore/etc/enstore-monitor.service >  \
 $ENSTORE_INSTALL_DIR/etc/enstore-monitor.service

pushd .
cd enstore/src
make enstore
cd $ENSTORE_INSTALL_DIR
cd ..
echo "MAKING ${VERS}.tgz"
tar -czf ${VERS}.tgz ${VERS}
mv ${VERS}.tgz ~/rpm/SOURCES/

# Create rpmbuild
rpmbuild -bb ~/rpm/SPECS/enstore_RH7_bin.spec || exit 1

# Tag 
#TVER="v${VERSION}-${REL}"  
#cd bill-calculator/
#git tag  -m ${TVER} -a ${TVER}
#git push origin ${TVER}
