SUMMARY = "Human detection service that publishes to MQTT"
DESCRIPTION = "Runs YOLOv4-tiny on a local TCP stream and publishes alerts."
LICENSE = "CLOSED"

# Add dependencies for Python, OpenCV, and MQTT
RDEPENDS:${PN} = " \
    python3-core \
    python3-opencv \
    python3-numpy \
    python3-paho-mqtt \
    python3-requests \
"

# List all the files we are installing
SRC_URI = " \
    file://human_detector.py \
    file://yolov4-tiny.weights \
    file://yolov4-tiny.cfg \
    file://coco.names \
    file://human-detector-cam1.service \
    file://human-detector-cam2.service \
"

inherit systemd

# Enable BOTH services on boot
# The 'systemd' class will read this variable and package these two files
SYSTEMD_SERVICE:${PN} = "human-detector-cam1.service human-detector-cam2.service"

do_install() {
    # Install the Python script
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/human_detector.py ${D}${bindir}/

    # Install the model files
    install -d ${D}${datadir}/human-detector
    install -m 0644 ${WORKDIR}/yolov4-tiny.weights ${D}${datadir}/human-detector/
    install -m 0644 ${WORKDIR}/yolov4-tiny.cfg ${D}${datadir}/human-detector/
    install -m 0644 ${WORKDIR}/coco.names ${D}${datadir}/human-detector/
    
    # Install the systemd service files
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/human-detector-cam1.service ${D}${systemd_system_unitdir}/
    install -m 0644 ${WORKDIR}/human-detector-cam2.service ${D}${systemd_system_unitdir}/
}

# --- CORRECTED SECTION ---
# Only list the files that are NOT automatically handled by an inherited class
FILES:${PN} += " \
    ${bindir}/human_detector.py \
    ${datadir}/human-detector/* \
"