#!/bin/bash
# Class 1 demo, as code: mount the persistent disk, install Docker, run the
# container with its state on that disk. Kill the VM, keep the disk, the
# state is still there.
#
# GCE runs this script on EVERY boot, so every step must be safe to repeat.
# Debug it on the VM with:  sudo journalctl -u google-startup-scripts -e
set -euo pipefail

DEVICE="/dev/disk/by-id/google-${disk_device_name}"
MOUNT_POINT="/mnt/disks/datos"

# Format only a brand-new disk (blkid finds no filesystem on it).
if ! blkid "$DEVICE" >/dev/null 2>&1; then
  mkfs.ext4 -F "$DEVICE"
fi

mkdir -p "$MOUNT_POINT"
grep -q " $MOUNT_POINT " /etc/fstab || echo "$DEVICE $MOUNT_POINT ext4 discard,defaults,nofail 0 2" >> /etc/fstab
mountpoint -q "$MOUNT_POINT" || mount "$MOUNT_POINT"
# Fail loudly: without the disk the container would write to the boot disk
# and the state would die with the VM.
mountpoint -q "$MOUNT_POINT"

%{ if data_uid > 0 ~}
# The image runs as uid ${data_uid} (not root): give it the data dir, or it
# cannot write its state and fails without a clear log line.
chown -R ${data_uid}:${data_uid} "$MOUNT_POINT"
%{ endif ~}

%{ if image == "" ~}
# Class 2: no container image yet -> the same nginx you installed by hand
# over SSH, now done by the VM itself at boot.
if ! command -v nginx >/dev/null 2>&1; then
  apt-get update
  apt-get install -y nginx
fi
# The page comes from nginx-index.html.tpl, rendered by OpenTofu: change it
# in code (var.nginx_title), never by hand on the VM.
cat > /var/www/html/index.html <<'HTML'
${nginx_index}
HTML
systemctl enable --now nginx
%{ else ~}
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

%{ if endswith(registry_host, "-docker.pkg.dev") ~}
# Private Artifact Registry image: docker needs credentials for it. This uses
# the VM's service account (it needs roles/artifactregistry.reader).
gcloud auth configure-docker "${registry_host}" --quiet
%{ endif ~}

# Stop cleanly first (SIGTERM, up to 30 s) so a stateful process such as
# Anvil can write its state before the container is replaced.
docker stop -t 30 ${container_name} >/dev/null 2>&1 || true
docker rm ${container_name} >/dev/null 2>&1 || true
docker run -d --name ${container_name} --restart unless-stopped \
  -p ${app_port}:${app_port} \
  -e DATA_DIR=/data \
  -e PORT=${app_port} \
  -v "$MOUNT_POINT":/data \
%{ if container_entrypoint != "" ~}
  --entrypoint ${container_entrypoint} \
%{ endif ~}
  ${image}%{ for a in container_args } ${a}%{ endfor }
%{ endif ~}
