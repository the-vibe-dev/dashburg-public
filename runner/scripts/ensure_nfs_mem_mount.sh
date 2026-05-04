#!/usr/bin/env bash
set -euo pipefail

NFS_HOST="${NFS_HOST:-nas.example.local}"
NFS_EXPORT_ROOT="${NFS_EXPORT_ROOT:-/volume1/AI}"
NFS_EXPORT_SHARED="${NFS_EXPORT_SHARED:-/volume1/AI/shared}"
MOUNT_ROOT="${MOUNT_ROOT:-/srv/dashburg}"
MOUNT_SHARED="${MOUNT_SHARED:-$MOUNT_ROOT/shared}"
RAW_SHARED_MOUNT="${RAW_SHARED_MOUNT:-/srv/dashburg_raw}"
MEM_FILE_NAME="${MEM_FILE_NAME:-MEM.md}"

FSTAB_MAIN_LINE="${NFS_HOST}:${NFS_EXPORT_ROOT} ${MOUNT_ROOT} nfs defaults,_netdev,nofail,x-systemd.automount,x-systemd.requires=network-online.target 0 0"
FSTAB_RAW_SHARED_LINE="${NFS_HOST}:${NFS_EXPORT_SHARED} ${RAW_SHARED_MOUNT} nfs defaults,_netdev,nofail,x-systemd.automount,x-systemd.requires=network-online.target 0 0"

have_sudo() {
  command -v sudo >/dev/null 2>&1
}

ensure_nfs_client() {
  if command -v mount.nfs >/dev/null 2>&1; then
    return 0
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "[nfs] mount.nfs is missing and apt-get is unavailable"
    return 1
  fi
  echo "[nfs] Installing nfs-common..."
  sudo apt-get update -y >/dev/null
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nfs-common >/dev/null
}

ensure_fstab_line() {
  local line="$1"
  local pattern="$2"
  if ! grep -qE "$pattern" /etc/fstab; then
    echo "$line" | sudo tee -a /etc/fstab >/dev/null
  fi
}

main() {
  if ! have_sudo; then
    echo "[nfs] sudo is required"
    exit 1
  fi

  ensure_nfs_client

  sudo mkdir -p "$MOUNT_ROOT" "$MOUNT_SHARED"
  sudo chmod 755 "$MOUNT_ROOT" "$MOUNT_SHARED" || true

  ensure_fstab_line \
    "$FSTAB_MAIN_LINE" \
    "^${NFS_HOST//./\\.}:${NFS_EXPORT_ROOT//\//\\/}[[:space:]]+${MOUNT_ROOT//\//\\/}[[:space:]]+nfs"

  sudo mount -a || true

  local mem_path="${MOUNT_SHARED}/${MEM_FILE_NAME}"
  if [ -r "$mem_path" ]; then
    echo "[nfs] Shared memory readable at $mem_path"
    exit 0
  fi

  echo "[nfs] Shared memory not readable via ${MOUNT_ROOT}; enabling raw-shared fallback"
  ensure_fstab_line \
    "$FSTAB_RAW_SHARED_LINE" \
    "^${NFS_HOST//./\\.}:${NFS_EXPORT_SHARED//\//\\/}[[:space:]]+${RAW_SHARED_MOUNT//\//\\/}[[:space:]]+nfs"

  sudo mkdir -p "$RAW_SHARED_MOUNT"
  sudo mount "$RAW_SHARED_MOUNT" || sudo mount -a || true

  if sudo test -f "${RAW_SHARED_MOUNT}/${MEM_FILE_NAME}"; then
    sudo cp "${RAW_SHARED_MOUNT}/${MEM_FILE_NAME}" "$mem_path"
    sudo chmod 644 "$mem_path" || true
  fi

  if [ -r "$mem_path" ]; then
    echo "[nfs] Fallback mirror ready at $mem_path"
    exit 0
  fi

  echo "[nfs] WARNING: ${mem_path} still unreadable; agents will fallback to ~/MEM.md"
  exit 0
}

main "$@"
