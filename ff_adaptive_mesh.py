import os
import re
import logging

LOG = '/usr/data/logs/firmwareExe.log'
LOG_TAIL_BYTES = 512 * 1024
MAX_SCAN_LINES = 10000

class FFAdaptiveMesh:
    def __init__(self, config):
        self.printer = config.get_printer()
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command(
            "FF_PREPARSE_OBJECTS", self.cmd_FF_PREPARSE_OBJECTS,
            desc="Pre-parse gcode file for EXCLUDE_OBJECT_DEFINE")

    def _find_gcode_file(self):
        try:
            with open(LOG, 'rb') as f:
                f.seek(0, os.SEEK_END)
                offset = max(0, f.tell() - LOG_TAIL_BYTES)
                f.seek(offset)
                data = f.read()
        except Exception:
            logging.exception("ff_adaptive_mesh: error reading log")
            return None
 
        lines = data.decode('utf-8', 'replace').splitlines()
        if offset and lines:
            del lines[0]

        print_path = None
        for line in reversed(lines):
            m = re.search(r'print path:\s*(.+?)\s*,\s*(?:isPaTest|$)', line)
            if m:
                print_path = m.group(1)
                break
        if not print_path:
            return None
        
        # if not 3mf, use directly
        if not print_path.lower().endswith('.3mf'):
            if os.path.isfile(print_path):
                return print_path
            logging.warning("ff_adaptive_mesh: print path not found: %r",
                            print_path)
            return None
        # find the extracted gcode from the 3mf
        for line in reversed(lines):
            m = re.search(r'Successfully extracted:(.+\.gcode)\s*$', line)
            if m:
                path = m.group(1)
                if os.path.isfile(path):
                    return path
                logging.warning("ff_adaptive_mesh: extracted gcode not found:"
                                " %r", path)
                return None
        return None

    def cmd_FF_PREPARSE_OBJECTS(self, gcmd):
        exclude_obj = self.printer.lookup_object('exclude_object', None)
        if exclude_obj is None:
            gcmd.respond_info("ff_adaptive_mesh: [exclude_object] not found in printer.cfg")
            return
        if exclude_obj.get_status(None).get("objects", []):
            return
        filepath = self._find_gcode_file()
        if not filepath:
            gcmd.respond_info("ff_adaptive_mesh: no gcode file found")
            return
        gcmd.respond_info("ff_adaptive_mesh: parsing %s"
                          % os.path.basename(filepath))
        objects = []
        seen_exec_block = False
        scanned = 0
        try:
            # looks for EXCLUDE_OBJECT_DEFINE lines at the top of the executable block
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for i, line in enumerate(f):
                    scanned = i + 1
                    line = line.strip()
                    if line.startswith('EXCLUDE_OBJECT_DEFINE '):
                        objects.append(line)
                    elif line.startswith('; EXECUTABLE_BLOCK_START'):
                        seen_exec_block = True
                    elif line.startswith(';start_gcode') or \
                            line.startswith('EXCLUDE_OBJECT_START'):
                        break  # reached start gcode / print body
                    elif i >= MAX_SCAN_LINES:
                        break  # none found
        except Exception:
            logging.exception("ff_adaptive_mesh: error reading file")
        if not objects:
            if seen_exec_block:
                msg = ("ff_adaptive_mesh: no EXCLUDE_OBJECT_DEFINE found. "
                       "Enable 'Exclude objects' in OrcaSlicer.")
                logging.info(msg)
            else:
                msg = ("ff_adaptive_mesh: EXECUTABLE_BLOCK_START not found in "
                       "first %d lines of %s; cannot pre-parse objects"
                       % (scanned, os.path.basename(filepath)))
                logging.warning(msg)
            gcmd.respond_info(msg)
            return
        for line in objects:
            try:
                self.printer.lookup_object('gcode').run_script_from_command(line)
            except Exception:
                logging.exception("ff_adaptive_mesh: error registering object")
        gcmd.respond_info("ff_adaptive_mesh: registered %d objects" % len(objects))

def load_config(config):
    return FFAdaptiveMesh(config)