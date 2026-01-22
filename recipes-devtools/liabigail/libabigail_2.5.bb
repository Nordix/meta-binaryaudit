SUMMARY = "The ABI Generic Analysis and Instrumentation Library"
HOMEPAGE = "https://sourceware.org/libabigail"
LICENSE = "LGPLv3"
SECTION = "devel"

SRC_URI = "https://mirrors.kernel.org/sourceware/libabigail/libabigail-${PV}.tar.xz"
SRC_URI[sha256sum] = "7cfc4e9b00ae38d87fb0c63beabb32b9cbf9ce410e52ceeb5ad5b3c5beb111f3"

LIC_FILES_CHKSUM = "file://LICENSE.txt;md5=0bcd48c3bdfef0c9d9fd17726e4b7dab"

DEPENDS += "elfutils libxml2"

S = "${WORKDIR}/libabigail-${PV}"

inherit autotools pkgconfig

PACKAGECONFIG ??= "${@bb.utils.contains('PACKAGE_CLASSES', 'package_rpm', 'rpm', '', d)} \
                   ${@bb.utils.contains('PACKAGE_CLASSES', 'package_deb', 'deb', '', d)} \
                   tar python3"

PACKAGECONFIG[rpm] = "--enable-rpm,--disable-rpm,rpm"
PACKAGECONFIG[deb] = "--enable-deb,--disable-deb,deb"
PACKAGECONFIG[tar] = "--enable-tar,--disable-tar,tar"
PACKAGECONFIG[apidoc] = "--enable-apidoc,--disable-apidoc,apidoc"
PACKAGECONFIG[manual] = "--enable-manual,--disable-manual,manual"
PACKAGECONFIG[bash-completion] = "--enable-bash-completion,--disable-bash-completion,bash-completion"
PACKAGECONFIG[fedabipkgdiff] = "--enable-fedabipkgdiff,--disable-fedabipkgdiff,fedabipkgdiff"
PACKAGECONFIG[python3] = "--enable-python3,--disable-python3,python3"

RDEPENDS:${PN} += "${@bb.utils.contains('PACKAGECONFIG', 'python3', 'python3', '', d)}"
RDEPENDS:${PN} += "${@bb.utils.contains('PACKAGECONFIG', 'deb', 'dpkg', '', d)}"

BBCLASSEXTEND = "native nativesdk"