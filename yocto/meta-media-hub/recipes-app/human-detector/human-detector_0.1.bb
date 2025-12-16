SUMMARY = "Human detection service that publishes to MQTT"
DESCRIPTION = "Runs YOLOv8 on Hailo with dual camera support."
LICENSE = "CLOSED"

RDEPENDS:${PN} = " \
    python3-core \
    python3-opencv \
    python3-numpy \
    python3-paho-mqtt \
    python3-requests \
    python3-threading \
    pyhailort \
"

SRC_URI = " \
    file://human_detector_manager.py \
    file://config.json \
    file://yolov8s.hef \
    file://human-detector.service \
"

inherit systemd

SYSTEMD_SERVICE:${PN} = "human-detector.service"

do_install() {
    # Install the Python Manager Script
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/human_detector_manager.py ${D}${bindir}/

    # Install the Config File
    install -d ${D}${sysconfdir}/human_detector
    install -m 0644 ${WORKDIR}/config.json ${D}${sysconfdir}/human_detector/

    # Install the Hailo Model
    install -d ${D}${datadir}/human-detector
    install -m 0644 ${WORKDIR}/yolov8s.hef ${D}${datadir}/human-detector/
    
    # Install the SINGLE systemd service
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/human-detector.service ${D}${systemd_system_unitdir}/
}

FILES:${PN} += " \
    ${bindir}/human_detector_manager.py \
    ${sysconfdir}/human_detector/config.json \
    ${datadir}/human-detector/* \
"