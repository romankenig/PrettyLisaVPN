"""Read physical Mach-O nlist tables, without nm's synthesized dyld symbols."""
import struct


def symbol_tables(data):
    if data[:4] == b"\xca\xfe\xba\xbe":
        tables = []
        count, = struct.unpack_from(">I", data, 4)
        if not 1 <= count <= 8:
            raise ValueError("Invalid universal architecture count")
        for index in range(count):
            cpu, _, offset, size, _ = struct.unpack_from(">IIIII", data, 8 + index * 20)
            if offset < 8 + count * 20 or size == 0 or offset + size > len(data):
                raise ValueError("Truncated universal slice")
            if data[offset:offset + 4] != b"\xcf\xfa\xed\xfe":
                raise ValueError("Expected a thin Mach-O universal slice")
            slice_tables = symbol_tables(data[offset:offset + size])
            if len(slice_tables) != 1 or slice_tables[0]["cpu"] != cpu:
                raise ValueError("Universal architecture mismatch")
            tables.extend(slice_tables)
        return tables
    if data[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("Expected a 64-bit little-endian Mach-O binary")
    cpu, = struct.unpack_from("<I", data, 4)
    commands, command_bytes = struct.unpack_from("<II", data, 16)
    offset, symtab = 32, None
    if offset + command_bytes > len(data):
        raise ValueError("Truncated load commands")
    for _ in range(commands):
        command, size = struct.unpack_from("<II", data, offset)
        if size < 8 or offset + size > 32 + command_bytes:
            raise ValueError("Invalid load command size")
        if command == 2:  # LC_SYMTAB
            if size != 24 or symtab is not None:
                raise ValueError("Invalid symbol table command")
            symtab = struct.unpack_from("<IIII", data, offset + 8)
        offset += size
    if symtab is None or offset != 32 + command_bytes:
        raise ValueError("Missing symbol table or inconsistent load commands")
    symbols, count, strings, string_bytes = symtab
    if symbols + count * 16 > len(data) or strings + string_bytes > len(data):
        raise ValueError("Truncated symbol or string table")
    external, local, debug, strip_markers = set(), [], 0, 0
    for index in range(count):
        name_index, kind, section, description, value = struct.unpack_from("<IBBHQ", data, symbols + index * 16)
        if name_index >= string_bytes:
            raise ValueError("Invalid symbol name index")
        end = data.find(b"\0", strings + name_index, strings + string_bytes)
        if end == -1:
            raise ValueError("Unterminated symbol name")
        name = data[strings + name_index:end].decode("utf-8")
        # Apple strip inserts this exact N_OPT sentinel at index zero to keep
        # indirect-symbol indexes nonzero (cctools strip.c, radar 5614542).
        # It is required linker metadata, not removable debug information.
        if (index, name, kind, section, description, value) == (
            0, "radr://5614542", 0x3c, 0, 0, 0x05614542
        ):
            strip_markers += 1
        elif kind & 0xe0:  # N_STAB: debugger records, not runtime exports.
            debug += 1
        elif not kind & 1:  # N_EXT
            local.append(name)
        elif kind & 0x0e:  # N_TYPE != N_UNDF: defined external symbol.
            external.add(name)
    return [{"cpu": cpu, "external": external, "local": local, "debug": debug,
             "strip_markers": strip_markers}]
