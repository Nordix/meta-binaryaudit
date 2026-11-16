SUMMARY = "The ABI Generic Analysis and Instrumentation Library"
HOMEPAGE = "https://sourceware.org/libabigail/"

LICENSE = "Apache-2.0-with-LLVM-exception"
LIC_FILES_CHKSUM = "file://LICENSE.txt;md5=0bcd48c3bdfef0c9d9fd17726e4b7dab"

SRC_URI = "http://mirrors.kernel.org/sourceware/${BPN}/${BP}.tar.xz \
           file://0001-configure-do-not-add-prefix-include-when-cross-compil.patch \
           file://0002-configure-use-DW_CFLAGS-to-look-for-elfutils-version.patch \
           "
SRC_URI[sha256sum] = "d34ea7c4b150f61e22edb1d16157e12c43fd18f8e8f09abce053d82ccaf92e06"

SECTION = "devel"

DEPENDS += "elfutils libxml2 xxhash xz"

python __anonymous() {
    if d.getVar("UNPACKDIR"):
        d.setVar("S", "${UNPACKDIR}/libabigail-${PV}")
    else:
        d.setVar("S", "${WORKDIR}/libabigail-${PV}")
}

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

PACKAGECONFIG:remove:class-native = "rpm deb"
PACKAGECONFIG:remove:class-nativesdk = "rpm deb"
PACKAGECONFIG:remove:class-target = "rpm deb"

BBCLASSEXTEND = "native nativesdk"