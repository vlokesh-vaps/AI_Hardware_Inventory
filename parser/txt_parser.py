"""
Robust Windows Health Check TXT Report Parser.
Parses reports using section headers and key-value extraction without depending on fixed line numbers.
"""
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from config import parser_logger, error_logger

class TxtParser:
    """Parses Windows hardware health-check text files into raw structured dictionaries."""

    SECTION_DIVIDER_PATTERN = re.compile(r"^={10,}|^-{10,}")
    KEY_VALUE_PATTERN = re.compile(r"^\s*([^:]+?)\s*:\s*(.*)$")
    
    # Sub-item header patterns
    NUMBERED_ITEM_PATTERN = re.compile(r"^(RAM STICK|DISK|CPU|MONITOR|SOFTWARE)\s+#(\d+)", re.IGNORECASE)
    DRIVE_ITEM_PATTERN = re.compile(r"^DRIVE:\s*([A-Za-z]:)", re.IGNORECASE)
    KNOWN_ENTITY_HEADERS = {
        "disk", "partition", "gpu", "keyboard", "mouse", "usb device", "network adapter", "desktop", "downloads", "pictures", "documents", "videos", "music"
    }

    # Section normalization mapping
    SECTION_MAP = {
        "computer / operating system": "computer_os",
        "cpu / processor": "cpu",
        "ram / memory": "ram",
        "motherboard": "motherboard",
        "bios / uefi": "bios",
        "physical storage / hdd / ssd": "physical_disks",
        "storage health": "storage_health",
        "drive / partition space": "drive_space",
        "physical partitions": "physical_partitions",
        "monitor / display": "monitors",
        "graphics / gpu": "gpu",
        "keyboard": "keyboards",
        "mouse / pointing device": "mice",
        "usb devices": "usb_devices",
        "network adapters": "network_adapters",
        "current physical user": "current_user",
        "user folder details": "user_folders",
        "installed software / applications": "installed_software",
        "temporary files": "temp_files",
        "temp / prefetch cleanup": "cleanup",
        "system uptime": "uptime",
        "important windows services": "services",
        "health check completed": "completion",
        # Simpler report format sections
        "windows health check report": "header",
        "cleanup status": "cleanup",
        "cpu info": "cpu_simple",
        "ram info": "ram_simple",
        "storage info": "storage_simple",
        "logged in user (physical console session)": "current_user_simple",
        "desktop folder size": "desktop_simple",
    }

    def parse(self, content_or_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parses the content of a TXT file or string into a structured raw dictionary.
        """
        if isinstance(content_or_path, (str, Path)) and Path(str(content_or_path)).is_file():
            parser_logger.info(f"Reading file: {content_or_path}")
            with open(content_or_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        elif isinstance(content_or_path, str):
            content = content_or_path
        else:
            raise ValueError("Invalid input provided to TxtParser: must be file path or string content.")

        if not content.strip():
            error_logger.error("Attempted to parse empty report.")
            raise ValueError("The report file is empty.")

        lines = content.splitlines()
        result: Dict[str, Any] = {
            "header": {},
            "sections": {}
        }

        # Step 1: Parse top-level header before the first major section
        line_idx = 0
        total_lines = len(lines)

        # Parse initial header (e.g. before "==== COMPUTER / OPERATING SYSTEM ====")
        while line_idx < total_lines:
            line = lines[line_idx].strip()
            # If line is divider and the next non-divider line looks like a section header
            if self.SECTION_DIVIDER_PATTERN.match(line):
                # Check if this starts a named section
                peek_idx = line_idx + 1
                while peek_idx < total_lines and not lines[peek_idx].strip():
                    peek_idx += 1
                if peek_idx < total_lines:
                    peek_title = lines[peek_idx].strip().lower()
                    if peek_title in self.SECTION_MAP:
                        break
            
            # Key-value match in top header
            kv_match = self.KEY_VALUE_PATTERN.match(lines[line_idx])
            if kv_match:
                k, v = kv_match.group(1).strip(), kv_match.group(2).strip()
                result["header"][k] = v

            line_idx += 1

        # Step 2: Parse sections
        current_section_name: Optional[str] = None
        current_section_lines: List[str] = []

        while line_idx < total_lines:
            line = lines[line_idx].strip()

            if self.SECTION_DIVIDER_PATTERN.match(line):
                # Peek to see section name
                peek_idx = line_idx + 1
                while peek_idx < total_lines and not lines[peek_idx].strip():
                    peek_idx += 1
                
                if peek_idx < total_lines:
                    candidate_title = lines[peek_idx].strip()
                    norm_candidate = candidate_title.lower()
                    if norm_candidate in self.SECTION_MAP:
                        # Save previous section if exists
                        if current_section_name:
                            result["sections"][current_section_name] = self._parse_section(
                                current_section_name, current_section_lines
                            )
                            current_section_lines = []
                        
                        current_section_name = self.SECTION_MAP[norm_candidate]
                        # Advance line_idx past the title line and trailing divider
                        line_idx = peek_idx + 1
                        while line_idx < total_lines and (self.SECTION_DIVIDER_PATTERN.match(lines[line_idx].strip()) or not lines[line_idx].strip()):
                            line_idx += 1
                        continue

            if current_section_name:
                current_section_lines.append(lines[line_idx])

            line_idx += 1

        # Save last section
        if current_section_name and current_section_lines:
            result["sections"][current_section_name] = self._parse_section(
                current_section_name, current_section_lines
            )

        parser_logger.info(
            f"Parsing completed. Detected sections: {list(result['sections'].keys())}"
        )
        return result

    def _parse_section(self, section_name: str, lines: List[str]) -> Any:
        """
        Parses lines within a recognized section, differentiating between single-object
        sections (e.g. Motherboard, BIOS) and multi-object lists (e.g. RAM, Disks, GPU, USB).
        """
        multi_item_sections = {
            "ram", "physical_disks", "storage_health", "drive_space", 
            "physical_partitions", "monitors", "gpu", "keyboards", 
            "mice", "usb_devices", "network_adapters", "installed_software", "services", "cpu"
        }

        if section_name in multi_item_sections:
            return self._parse_multi_item_section(section_name, lines)
        else:
            return self._parse_single_item_section(lines)

    def _parse_single_item_section(self, lines: List[str]) -> Dict[str, Any]:
        """Parses a section that contains single key-value mappings."""
        data: Dict[str, Any] = {}
        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("Note:") or line_str.startswith("END OF"):
                continue
            kv = self.KEY_VALUE_PATTERN.match(line)
            if kv:
                k, v = kv.group(1).strip(), kv.group(2).strip()
                data[k] = v
        return data

    def _parse_multi_item_section(self, section_name: str, lines: List[str]) -> Dict[str, Any]:
        """
        Parses a section with repeated items (like RAM STICK #1, DISK #1, GPU, USB Device).
        Returns a dict containing 'items': [list of dicts] and 'meta': {section metadata}.
        """
        items: List[Dict[str, Any]] = []
        meta: Dict[str, Any] = {}
        current_item: Optional[Dict[str, Any]] = None

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("Note:") or stripped.startswith("Collecting installed software"):
                continue

            # Check if this line starts a service item: "Service : WinRM"
            if section_name == "services" and stripped.lower().startswith("service"):
                kv = self.KEY_VALUE_PATTERN.match(line)
                if kv and kv.group(1).strip().lower() == "service":
                    if current_item is not None:
                        items.append(current_item)
                    current_item = {"Service": kv.group(2).strip()}
                    continue

            # Check for numbered item header: RAM STICK #1, DISK #1, CPU #1, MONITOR #1, SOFTWARE #1
            num_match = self.NUMBERED_ITEM_PATTERN.match(stripped)
            if num_match:
                if current_item is not None:
                    items.append(current_item)
                current_item = {
                    "_item_type": num_match.group(1).strip(),
                    "_item_index": int(num_match.group(2))
                }
                continue

            # Check for DRIVE: C:
            drive_match = self.DRIVE_ITEM_PATTERN.match(stripped)
            if drive_match:
                if current_item is not None:
                    items.append(current_item)
                current_item = {"Drive": drive_match.group(1).strip().upper()}
                continue

            # Check for single word item header: Disk, Partition, GPU, Keyboard, Mouse, USB Device, Network Adapter
            if stripped.lower() in self.KNOWN_ENTITY_HEADERS:
                if current_item is not None:
                    items.append(current_item)
                current_item = {"_item_type": stripped}
                continue

            # Normal Key : Value line
            kv = self.KEY_VALUE_PATTERN.match(line)
            if kv:
                k = kv.group(1).strip()
                v = kv.group(2).strip()
                if current_item is not None:
                    current_item[k] = v
                else:
                    # Section-level meta property, e.g. "Number of RAM Sticks : 2" or "TOTAL INSTALLED SOFTWARE : 279"
                    meta[k] = v
            else:
                # Handle space-separated table rows in simpler format if applicable
                pass

        if current_item is not None:
            items.append(current_item)

        return {
            "meta": meta,
            "items": items
        }
