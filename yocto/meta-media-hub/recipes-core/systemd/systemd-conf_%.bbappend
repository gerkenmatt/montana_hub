FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://ap.network"

FILES_${PN} += "/etc/systemd/network/ap.network"

# Using colon-append as a last resort for older/stricter parsers
do_install:append () {
        install -d ${D}${sysconfdir}/systemd/network
        install -m 0644 ${WORKDIR}/ap.network ${D}${sysconfdir}/systemd/network/
}