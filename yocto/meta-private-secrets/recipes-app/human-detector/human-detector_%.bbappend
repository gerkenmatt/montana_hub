FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://detector.env"

do_install:append() {
    install -d ${D}${sysconfdir}
    install -m 0600 ${WORKDIR}/detector.env ${D}${sysconfdir}/
}

FILES:${PN} += "${sysconfdir}/detector.env"
CONFFILES:${PN} += "${sysconfdir}/detector.env"