"""
Unit tests for TXT Parser and Normalizer.
Validates extraction of CPU, RAM, Storage, GPU, Monitor, USB, Network,
as well as resilience to missing fields and malformed files.
"""
import pytest
from pathlib import Path
from parser.txt_parser import TxtParser
from parser.normalizer import DataNormalizer

SAMPLE_FILE_1 = Path(r"C:\Users\admin\Downloads\1_2026-09-03_17-51-08.txt")
SAMPLE_FILE_2 = Path(r"C:\healthcheck\1_2026-09-03_17-56-27.txt")

SYNTHETIC_REPORT = r"""WINDOWS COMPLETE HARDWARE SOFTWARE HEALTH CHECK
================================================
IP Address         : 192.168.1.50
All IPv4 Addresses : 192.168.1.50
Computer Name      : TEST-PC-01
Report Date        : 2026-09-05 10:00:00
Report File        : C:\healthcheck\test.txt

==========================================================================================
 COMPUTER / OPERATING SYSTEM
==========================================================================================
Computer Name        : TEST-PC-01
Manufacturer         : HP
Model                : EliteDesk 800 G4
System Type          : x64-based PC
Domain / Workgroup   : WORKGROUP
Logged On User       : TEST-PC-01\User
Total Physical RAM   : 16.0 GB
Operating System     : Windows 11 Enterprise
OS Version           : 10.0.22631
OS Build             : 22631
Architecture         : 64-bit
Windows Serial       : 12345-67890-ABCDE
Install Date         : 01/10/2026 10:00:00
Last Boot            : 09/01/2026 08:00:00

==========================================================================================
 CPU / PROCESSOR
==========================================================================================
CPU #1
  Name               : Intel(R) Core(TM) i7-8700 CPU @ 3.20GHz
  Manufacturer       : GenuineIntel
  Model              : Intel64
  Processor ID       : BFEBFBFF000906EA
  Serial Number      : N/A
  Socket             : LGA1151
  Current Speed      : 3200 MHz
  Maximum Speed      : 3200 MHz
  Cores              : 6
  Threads            : 12
  Architecture       : 9
  Status             : OK

==========================================================================================
 RAM / MEMORY
==========================================================================================
Number of RAM Sticks : 2

RAM STICK #1
  Manufacturer       : Samsung
  Model / Part No    : M378A1K43CB2
  Serial Number      : RAM_SN_001
  Capacity           : 8 GB
  Speed              : 2666 MHz
  Configured Speed   : 2666 MHz
  Device Locator     : DIMM1

RAM STICK #2
  Manufacturer       : Samsung
  Model / Part No    : M378A1K43CB2
  Serial Number      : RAM_SN_002
  Capacity           : 8 GB
  Speed              : 2666 MHz
  Configured Speed   : 2666 MHz
  Device Locator     : DIMM2

==========================================================================================
 PHYSICAL STORAGE / HDD / SSD
==========================================================================================
Number of Physical Disks : 1

DISK #1
  Device              : \\\\.\\PHYSICALDRIVE0
  Model               : Samsung SSD 860 EVO 500GB
  Manufacturer        : Samsung
  Serial Number       : S3Z9NB0K123456
  Firmware Revision   : RVT04B6Q
  Interface           : IDE
  Media Type          : Fixed hard disk media
  Size                : 465.76 GB
  Status              : OK
  Partitions          : 2

==========================================================================================
 STORAGE HEALTH
==========================================================================================
Disk
  Friendly Name       : Samsung SSD 860 EVO 500GB
  Model               : Samsung SSD 860 EVO 500GB
  Manufacturer        : Samsung
  Serial Number       : S3Z9NB0K123456
  Media Type          : SSD
  Bus Type            : SATA
  Size                : 465.76 GB
  Health Status       : Healthy
  Operational Status  : OK

==========================================================================================
 DRIVE / PARTITION SPACE
==========================================================================================
DRIVE: C:
  Volume Name        : System
  File System        : NTFS
  Total Size         : 465.0 GB
  Used Space         : 200.0 GB
  Free Space         : 265.0 GB
  Free Percentage    : 56.98 %

==========================================================================================
 MONITOR / DISPLAY
==========================================================================================
MONITOR #1
  Manufacturer       : Dell
  Model               : P2419H
  Product Code        : DEL40BB
  Serial Number       : MON_SN_9988

==========================================================================================
 GRAPHICS / GPU
==========================================================================================
GPU
  Name                : NVIDIA GeForce GTX 1050 Ti
  Manufacturer        : NVIDIA
  Driver Version      : 31.0.15.3623
  Video Memory        : 4 GB
  Video Processor     : GeForce GTX 1050 Ti
  Resolution          : 1920 x 1080
  Refresh Rate        : 60 Hz

==========================================================================================
 KEYBOARD
==========================================================================================
Keyboard
  Name                : Standard PS/2 Keyboard
  Description         : Keyboard Device
  Manufacturer        : Standard
  Device ID           : HID\\VID_046D&PID_C31C
  Status              : OK

==========================================================================================
 MOUSE / POINTING DEVICE
==========================================================================================
Mouse
  Name                : Optical USB Mouse
  Description         : Pointing Device
  Manufacturer        : Logitech
  Device ID           : HID\\VID_046D&PID_C077
  Hardware Type       : USB
  Status              : OK

==========================================================================================
 USB DEVICES
==========================================================================================
USB Device
  Name                : USB Flash Drive
  Manufacturer        : SanDisk
  Device ID           : USB\\VID_0781&PID_5583
  PNP Device ID       : USB\\VID_0781&PID_5583\\123456
  Status              : OK

==========================================================================================
 NETWORK ADAPTERS
==========================================================================================
Network Adapter
  Name                : Intel(R) Ethernet Connection I219-LM
  Manufacturer        : Intel
  MAC Address         : 00:1A:2B:3C:4D:5E
  Adapter Type        : Ethernet 802.3
  Speed               : 1000000000
  Device ID           : 1
  Status              : 2

==========================================================================================
 MOTHERBOARD
==========================================================================================
Manufacturer         : HP
Product / Model      : 843B
Version              : KBC Version 07.D2.00
Serial Number        : MB_SN_5566
Part Number          : N/A
Status               : OK

==========================================================================================
 BIOS / UEFI
==========================================================================================
Manufacturer         : HP
BIOS Version         : Q02 Ver. 02.14.01
BIOS Version 2       : 02.14.01
BIOS Serial Number   : BIOS_SN_7788
Release Date         : 04/15/2021
SMBIOS Major         : 3
SMBIOS Minor         : 2
"""

@pytest.fixture
def parser():
    return TxtParser()

@pytest.fixture
def normalizer():
    return DataNormalizer()

def test_parse_synthetic_report(parser, normalizer):
    """Tests comprehensive extraction of all hardware components from synthetic report."""
    raw = parser.parse(SYNTHETIC_REPORT)
    assert "sections" in raw
    assert "cpu" in raw["sections"]
    assert "ram" in raw["sections"]
    assert "physical_disks" in raw["sections"]

    norm = normalizer.normalize(raw, "synthetic.txt")
    
    # Computer & Asset Metadata
    assert norm["asset"]["computer_name"] == "TEST-PC-01"
    assert norm["asset"]["manufacturer"] == "HP"
    assert norm["asset"]["model"] == "EliteDesk 800 G4"
    assert norm["asset"]["ip_address"] == "192.168.1.50"

    # CPU
    assert len(norm["cpu"]) == 1
    cpu = norm["cpu"][0]
    assert cpu["cores"] == 6
    assert cpu["threads"] == 12
    assert cpu["current_speed_mhz"] == 3200
    assert cpu["status"] == "OK"

    # RAM
    assert len(norm["ram"]) == 2
    assert norm["total_ram_gb"] == 16.0
    assert norm["ram"][0]["serial_number"] == "RAM_SN_001"
    assert norm["ram"][1]["serial_number"] == "RAM_SN_002"

    # Storage & Health merge
    assert len(norm["storage"]) == 1
    disk = norm["storage"][0]
    assert disk["model"] == "Samsung SSD 860 EVO 500GB"
    assert disk["media_type"] == "SSD"
    assert disk["health_status"] == "Healthy"
    assert disk["operational_status"] == "OK"

    # Drives
    assert len(norm["drives"]) == 1
    drive = norm["drives"][0]
    assert drive["drive_letter"] == "C:"
    assert drive["free_percentage"] == 56.98
    assert drive["status"] == "NORMAL"

    # GPU
    assert len(norm["gpu"]) == 1
    assert "GeForce GTX 1050 Ti" in norm["gpu"][0]["name"]
    assert norm["gpu"][0]["video_memory"] == "4 GB"

    # Monitor
    assert len(norm["monitors"]) == 1
    assert norm["monitors"][0]["model"] == "P2419H"
    assert norm["monitors"][0]["serial_number"] == "MON_SN_9988"

    # Keyboard & Mouse
    assert len(norm["keyboards"]) == 1
    assert norm["keyboards"][0]["name"] == "Standard PS/2 Keyboard"
    assert len(norm["mice"]) == 1
    assert norm["mice"][0]["name"] == "Optical USB Mouse"

    # USB
    assert len(norm["usb_devices"]) == 1
    assert norm["usb_devices"][0]["name"] == "USB Flash Drive"

    # Network
    assert len(norm["network_adapters"]) == 1
    assert norm["network_adapters"][0]["mac_address"] == "00:1A:2B:3C:4D:5E"

    # Motherboard & BIOS
    assert norm["motherboard"]["model"] == "843B"
    assert norm["bios"]["bios_version"] == "Q02 Ver. 02.14.01"

def test_parse_real_sample_file(parser, normalizer):
    """Tests parsing against real sample report if present on disk."""
    if not SAMPLE_FILE_1.exists():
        pytest.skip(f"Sample file {SAMPLE_FILE_1} not present on test machine")

    raw = parser.parse(SAMPLE_FILE_1)
    norm = normalizer.normalize(raw, SAMPLE_FILE_1.name)

    assert norm["asset"]["computer_name"] == "2F-S03"
    assert norm["asset"]["manufacturer"] == "Dell Inc."
    assert norm["asset"]["model"] == "OptiPlex 7060"
    assert norm["total_ram_gb"] == 23.8
    assert len(norm["ram"]) == 2
    assert len(norm["storage"]) == 2
    assert len(norm["gpu"]) == 2
    assert len(norm["monitors"]) == 1
    assert len(norm["usb_devices"]) >= 5
    assert norm["software_count"] == 279

def test_empty_file_handling(parser):
    """Empty files must raise a clear ValueError."""
    with pytest.raises(ValueError, match="empty"):
        parser.parse("   \n\t  ")

def test_missing_fields_handling(parser, normalizer):
    """Parser must handle incomplete reports gracefully without crashing."""
    incomplete = """WINDOWS COMPLETE HARDWARE SOFTWARE HEALTH CHECK
================================================
Computer Name : BARE-PC

==========================================================================================
 COMPUTER / OPERATING SYSTEM
==========================================================================================
Computer Name : BARE-PC
"""
    raw = parser.parse(incomplete)
    norm = normalizer.normalize(raw, "bare.txt")
    assert norm["asset"]["computer_name"] == "BARE-PC"
    assert norm["asset"]["manufacturer"] == "N/A"
    assert norm["cpu"] == []
    assert norm["ram"] == []
    assert norm["storage"] == []
