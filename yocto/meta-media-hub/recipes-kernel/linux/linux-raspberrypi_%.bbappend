FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI += "\
	file://4k-pages.cfg \
	file://defconfig \
"

# Unset the machine-specific variable that is causing the conflict
KBUILD_DEFCONFIG:raspberrypi5 = ""

# Force Yocto to use our custom defconfig instead of the board default
KBUILD_DEFCONFIG = ""