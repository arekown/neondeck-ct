"""Findet den Loupedeck CT ueber sysfs (USB 2ec2:0003, zweite Hardware-Revision 2ec2:0007)."""
from pathlib import Path

VENDOR_ID = "2ec2"
PRODUCT_IDS = ("0003", "0007")  # 0007: spaetere CT-Revision (LoupixDeck, Bitfocus Companion)


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def list_cts(sys_root: str = "/sys/class/tty") -> list[tuple[str, str]]:
    """Alle angeschlossenen CTs als ``(/dev/ttyACM…, Produkt-ID)``."""
    found = []
    for entry in sorted(Path(sys_root).glob("ttyACM*")):
        usb = entry / "device" / ".."  # ".." bleibt stehen: der Kernel loest den Link auf
        product = _read(usb / "idProduct")
        if _read(usb / "idVendor") == VENDOR_ID and product in PRODUCT_IDS:
            found.append(("/dev/" + entry.name, product))
    return found


def find_ct(sys_root: str = "/sys/class/tty") -> str | None:
    """Pfad des ersten passenden /dev/ttyACM*, sonst None."""
    found = list_cts(sys_root)
    return found[0][0] if found else None
