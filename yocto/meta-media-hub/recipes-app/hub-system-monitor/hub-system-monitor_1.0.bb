SUMMARY = "Hub System Monitor Service"
DESCRIPTION = "Reports system health (CPU, Temp, RAM) to MQTT and handles remote reboot commands."
LICENSE = "CLOSED"

SRC_URI = " \
    file://hub_system_monitor.py \
    file://hub-system-monitor.service \
"

# Ensure Python and required libraries are installed
RDEPENDS:${PN} = " \
    python3-core \
    python3-psutil \
    python3-paho-mqtt \
"

inherit systemd

SYSTEMD_SERVICE:${PN} = "hub-system-monitor.service"

do_install() {
    # Install the Python script to /usr/bin
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/hub_system_monitor.py ${D}${bindir}/

    # Install the Systemd Service
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/hub-system-monitor.service ${D}${systemd_system_unitdir}/
}

FILES:${PN} += " \
    ${bindir}/hub_system_monitor.py \
    ${systemd_system_unitdir}/hub-system-monitor.service \
"