# FlashForge Adventurer 5 Series — Root & Mods

Root access and quality-of-life mods for the FlashForge C5 / Adventurer 5 series (Klipper-based firmware).

## Credits

All of the research, scripts and mods documented here are the work of **ano** [ano.space] on Discord. This repository is only a write-up of their findings — full credit goes to them.

> [!WARNING]
> Everything here modifies your printer's firmware and voids your warranty. You are responsible for your own machine. Read a section fully before running any of it.

> [!IMPORTANT]
> Every script and config file you put on the printer **must be saved with Unix line endings (LF)**. Windows CRLF endings will silently break them.

---

## Table of contents

- [Getting root](#getting-root)
- [Kernel patch: legacy NaN binaries](#kernel-patch-legacy-nan-binaries)
- [Adaptive bed meshing](#adaptive-bed-meshing)
- [Moonraker & Mainsail](#moonraker--mainsail)
- [Blocking OTA updates](#blocking-ota-updates)
- [Changelog](#changelog)

---

## Getting root

### Requirements

- A **USB flash drive**, formatted to **FAT32**
  - USB 3.1 drives may not work. If you run into problems, try a USB 2.0 drive.
- The printer **connected to your network**, so you can SSH into it afterwards
- `runFirmwareExe.sh` — see [`mods` → *Get Root*](#) <!-- TODO: replace with real link -->

### Steps

1. Format the USB drive to **FAT32**.
2. Place `runFirmwareExe.sh` in the **root** of the drive.
3. Turn the printer **off**, plug the drive in, then **power it on**.
4. It will hang forever on the FlashForge boot logo. **Wait about 1 minute** to make sure the script has run.
5. Turn the printer **off**, unplug the drive, then power it on again.

### Logging in

```bash
ssh pwned@<printer-ip>
```

| | |
|---|---|
| **User** | `pwned` |
| **Password** | `letmein` |

The home directory is `/usr/data/home/pwned` so that it is writable (not read-only).

---

## Kernel patch: legacy NaN binaries

The kernel used in the C5 series is compiled to only run binaries built with `EF_MIPS_NAN2008`. That's a problem, because very few prebuilt packages carry that flag — you'd have to compile them yourself.

The workaround: patch a magic offset in memory on every boot so the kernel accepts legacy-NaN binaries. Specifically, this patches [`elf.c`'s NaN handling field](https://github.com/torvalds/linux/blob/59dee6d28756c629f3a0bb56266f80e36ef7c99c/arch/mips/kernel/elf.c#L164). The equivalent of this patch is setting `ieee754=relaxed`.

> [!CAUTION]
> The offset **depends on your kernel package version**. Only apply this if your version matches one in the table below.

### 1. Check your kernel package version

```bash
ls /usr/prog/PROGRAM/kernel/
```

Take the **highest** version number and look it up here:

| Kernel package version | Offset |
|---|---|
| `2.0.1` | `0x00a130d1` |

### 2. Verify the offset

This only reads, it does not write anything:

```bash
busybox devmem <offset> 8
```

It should return `0x0`. If it does, you're good to continue.

### 3. Apply on every boot

Add this to the **top** of `/usr/prog/app_startup.sh`, directly after the shebang:

```sh
# allow legacy nan binaries to run
busybox devmem <offset> 8 1
```

This technically allows non-standard NaN handling for legacy-NaN binaries, but the vast majority of binaries are unaffected. As far as I know this is the best available approach — the alternatives are recompiling the kernel or changing bootargs via U-Boot over UART.

---

## Adaptive bed meshing

By default, enabling **Leveling before print** in the slicer performs a *full* bed mesh. This mod makes that option use **adaptive** bed meshing instead, by making the `BED_MESH_CALIBRATE` macro always mesh adaptively when possible.

It's an admittedly odd way of achieving this, but unless you move off FlashForge's software entirely (e.g. starting prints through Moonraker), this is the best option available.

**Needed:** `ff_adaptive_mesh.py` — see [`mods` → *Adaptive bed meshing*](#) <!-- TODO: replace with real link -->

### 1. Optional: heat-soak time

`/usr/data/firmwareRes/config/test.json` has an option called `keepBedTempPrint`. It controls how long the bed heat-soaks before leveling, in **minutes**. Set it to `0` to disable heat-soaking.

### 2. Install the Klipper extra

Place `ff_adaptive_mesh.py` in:

```
/usr/prog/klipper/klippy/extras
```

### 3. Add the macro hooks

Add the following to `/usr/data/config/printer.macro.cfg` (Unix line endings!):

```ini
; adaptive mesh hooks
[gcode_macro BED_MESH_CALIBRATE]
rename_existing: _BED_MESH_CALIBRATE
variable_adaptive_done: 0
gcode:
    FF_PREPARSE_OBJECTS
    _BED_MESH_CALIBRATE ADAPTIVE=1
    SET_GCODE_VARIABLE MACRO=BED_MESH_CALIBRATE VARIABLE=adaptive_done VALUE=1

[gcode_macro BED_MESH_PROFILE]
rename_existing: _BED_MESH_PROFILE
gcode:
    {% if 'LOAD' in params and printer["gcode_macro BED_MESH_CALIBRATE"].adaptive_done == 1 %}
        {action_respond_info("ff_adaptive: skipping profile load, keeping adaptive mesh")}
        SET_GCODE_VARIABLE MACRO=BED_MESH_CALIBRATE VARIABLE=adaptive_done VALUE=0
    {% else %}
        _BED_MESH_PROFILE {rawparams}
    {% endif %}
```

If you want a custom margin, change `_BED_MESH_CALIBRATE ADAPTIVE=1` to also pass `ADAPTIVE_MARGIN=<x>`.

### 4. Enable the module

Add to your `printer.cfg`:

```ini
[ff_adaptive_mesh]
```

### 5. Enable "Exclude objects" in the slicer

In Orca Slicer, turn on **Exclude objects**. Without it, the printer falls back to full bed meshing.

---

## Moonraker & Mainsail

Mainsail is very unhappy if you aren't using its own configs. A modified `mainsail.cfg` with the SD-card parts disabled (they conflict) is provided.

> [!NOTE]
> Don't actually use any of the commands in that config directly. They exist purely to stop Mainsail from complaining.

### 1. Include the config

After uploading `mainsail.cfg`, add this near the top of `printer.cfg` — probably below the rest of the includes:

```ini
[include mainsail.cfg]
```

### 2. Enable the services

In `/usr/prog/klipper/start.sh`, uncomment these two lines at the bottom by removing the leading `#`:

```sh
#/usr/prog/nginx/sbin/nginx -p /usr/prog/nginx -c /usr/prog/nginx/conf/nginx.conf
#/usr/prog/klipper/moonrakerDaemon start
```

### 3. Reboot

| Service | Port |
|---|---|
| Mainsail | `80` |
| Moonraker | `7125` |

---

## Blocking OTA updates

Updates can overwrite `/etc/passwd` and other changes you've made. Even in LAN-only mode the printer reaches out over WAN to check for updates — automatically on startup and whenever you check manually.

Add these entries to `/etc/hosts`:

```
127.0.0.1 update.flashforge.com
127.0.0.1 update.sz3dp.com
127.0.0.1 update.cn.sz3dp.com
```

---

## Changelog

### `runFirmwareExe.sh`

- **16 days ago** — home directory is now set to `/usr/data/home/pwned` so it isn't read-only.

### `ff_adaptive_mesh.py`

- **4 days ago** — fixed failing on G-code files with large start blocks, and failing to detect G-code files with spaces in their filename.
