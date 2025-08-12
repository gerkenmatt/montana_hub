# human-detector_0.1.bb

SUMMARY = "Human detection application for camera hub"
DESCRIPTION = "A Python application that uses GStreamer and OpenCV to detect humans in RTSP streams and send email alerts."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

# Source files are all local to the recipe
SRC_URI = " \
    file://human_detector.py \
    file://yolov4-tiny.weights \
    file://yolov4-tiny.cfg \
    file://coco.names \
    file://human-detector.service \
"

# This recipe depends on python3 and opencv being present on the target
RDEPENDS:${PN} = "python3 python3-opencv"

# Inherit the systemd class to handle service installation and enablement
inherit systemd

# Specify the name of the service file associated with this package
SYSTEMD_SERVICE:${PN} = "human-detector.service"

# This recipe does not have a configure or compile step, only an install step.
# The S variable points to the work directory where SRC_URI files are placed.
S = "${WORKDIR}"

# The do_install task specifies how to install the files into the target rootfs
do_install() {
    # Install the main application script
    install -d ${D}${bindir}
    install -m 0755 ${S}/human_detector.py ${D}${bindir}/

    # Install the DNN model files to a shared location
    install -d ${D}${datadir}/human-detector
    install -m 0644 ${S}/yolov4-tiny.weights ${D}${datadir}/human-detector/
    install -m 0644 ${S}/yolov4-tiny.cfg ${D}${datadir}/human-detector/
    install -m 0644 ${S}/coco.names ${D}${datadir}/human-detector/

    # Install the systemd service file
    install -d ${D}${systemd_unitdir}/system
    install -m 0644 ${S}/human-detector.service ${D}${systemd_unitdir}/system/
}

# Ensure the installed files are included in the final package
FILES:${PN} += " \
    ${bindir}/human_detector.py \
    ${datadir}/human-detector/yolov4-tiny.weights \
    ${datadir}/human-detector/yolov4-tiny.cfg \
    ${datadir}/human-detector/coco.names \
"