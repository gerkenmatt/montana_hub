SUMMARY = "FFmpeg RTSP to TCP Streaming Service for Wyze Cams"
DESCRIPTION = "A systemd service to permanently stream from a Wyze camera using ffmpeg."
LICENSE = "CLOSED"

# Source file is local to the recipe
SRC_URI = "file://ffmpeg-stream.service"

# Inherit the systemd class to handle service installation and enablement
inherit systemd

# Specify the name of the service file associated with this package
SYSTEMD_SERVICE:${PN} = "ffmpeg-stream.service"

# Point S to the work directory where SRC_URI files are placed
S = "${WORKDIR}"

# Manually define the installation steps, mirroring the working recipe
do_install() {
    install -d ${D}${systemd_unitdir}/system
    install -m 0644 ${S}/ffmpeg-stream.service ${D}${systemd_unitdir}/system/
}