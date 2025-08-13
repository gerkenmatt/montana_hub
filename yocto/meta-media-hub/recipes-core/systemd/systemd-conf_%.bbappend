FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += " \
    file://ap.network \
    file://eth0.network \
    "

FILES:${PN} += " \
    /etc/systemd/network/ap.network \
    /etc/systemd/network/eth0.network \
    "

do_install:append() {
    install -d ${D}${sysconfdir}/systemd/network
    install -m 0644 ${WORKDIR}/ap.network ${D}${sysconfdir}/systemd/network/
    install -m 0644 ${WORKDIR}/eth0.network ${D}${sysconfdir}/systemd/network/
}