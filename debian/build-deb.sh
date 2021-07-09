#!/bin/bash
# Should be run from the root of the source tree
# Set env var REVISION to overwrite the 'revision' field in version string

if [ ! -d debian ]; then
   echo "Directory 'debian' not found"
   exit 1
fi
if [ ! -f debian/changelog.in ]; then
   echo "Debian changelog file not found"
   exit 1
fi

# Build python2 package
BUILD_DIR=${BUILD_DIR:-`pwd`/debbuild}
mkdir -p $BUILD_DIR
rm -rf $BUILD_DIR/*
NAME=`python setup.py --name`
VERSION_PY=`python setup.py --version`
VERSION=`echo $VERSION_PY | sed -nre 's,([^\.]+.[^\.]+.[^\.]+)((\.)(0[^\.]+))?((\.)(dev.*))?,\1 \4 \7,p' | sed -re 's/ *$//g' | sed -re 's/ +/~/g'`
REVISION=${REVISION:-1}
python setup.py sdist --dist-dir $BUILD_DIR
SOURCE_FILE=${NAME}-${VERSION_PY}.tar.gz
tar -C $BUILD_DIR -xf $BUILD_DIR/$SOURCE_FILE
SOURCE_DIR=$BUILD_DIR/${NAME}-${VERSION_PY}
cp -H -r debian $SOURCE_DIR/
sed -e "s/@VERSION@/$VERSION/" -e "s/@REVISION@/$REVISION/" ${SOURCE_DIR}/debian/changelog.in > ${SOURCE_DIR}/debian/changelog

mv $BUILD_DIR/$SOURCE_FILE $BUILD_DIR/${NAME}_${VERSION}.orig.tar.gz
pushd ${SOURCE_DIR}
debuild -d -us -uc
popd

# Save the python2 package
cp debbuild/*.deb .
rm -rf debbuild

# Prepare build scripts for python3
cp debian/control .
cp debian/rules .
sed -i "s/python/python3/g" debian/control
sed -i "s/Package: aci-integration-module/Package: python3-aci-integration-module/g" debian/control
sed -i "s/Python2.7/Python3/g" debian/control
sed -i "s/2.7/3.3/g" debian/control
sed -i "s/acitoolkit/python3-acitoolkit/g" debian/control
sed -i "s/python2/python3/g" debian/rules

# Build the python3 package
BUILD_DIR=${BUILD_DIR:-`pwd`/debbuild}
mkdir -p $BUILD_DIR
rm -rf $BUILD_DIR/*
NAME=`python3 setup.py --name`
VERSION_PY=`python3 setup.py --version`
VERSION=`echo $VERSION_PY | sed -nre 's,([^\.]+.[^\.]+.[^\.]+)((\.)(0[^\.]+))?((\.)(dev.*))?,\1 \4 \7,p' | sed -re 's/ *$//g' | sed -re 's/ +/~/g'`
REVISION=${REVISION:-1}
python3 setup.py sdist --dist-dir $BUILD_DIR
SOURCE_FILE=${NAME}-${VERSION_PY}.tar.gz
tar -C $BUILD_DIR -xf $BUILD_DIR/$SOURCE_FILE
SOURCE_DIR=$BUILD_DIR/${NAME}-${VERSION_PY}
cp -H -r debian $SOURCE_DIR/
sed -e "s/@VERSION@/$VERSION/" -e "s/@REVISION@/$REVISION/" ${SOURCE_DIR}/debian/changelog.in > ${SOURCE_DIR}/debian/changelog

mv $BUILD_DIR/$SOURCE_FILE $BUILD_DIR/${NAME}_${VERSION}.orig.tar.gz
pushd ${SOURCE_DIR}
debuild -d -us -uc
popd

# restore the original files and debian packages
mv control debian/control
mv rules debian/rules
mv *.deb debbuild/
