#!/bin/sh
# Note: put this in wz_mini/usr/bin/ 
touch /opt/wz_mini/log/custom_script_ran.txt
killall -q wpa_supplicant udhcpc
rm -f /var/run/wpa_supplicant/wlan0


until ifconfig wlan0 >/dev/null 2>&1; do sleep 1; done
ifconfig wlan0 up


# Realtek 8189fs is happier if wext is allowed as a fallback
wpa_supplicant -B -i wlan0 -D nl80211,wext -c /opt/wz_mini/etc/wpa_supplicant.conf


# wait briefly for 4-way handshake
i=0
until wpa_cli -i wlan0 status | grep -q '^wpa_state=COMPLETED'; do
  sleep 1; i=$((i+1)); [ $i -gt 20 ] && break
done


# get IPv4 from your Pi's dnsmasq
udhcpc -i wlan0 -x hostname:WCV3 -b -s /opt/wz_mini/usr/bin/udhcpc.script
